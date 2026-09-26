import unittest
from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.demand_service import (
    DEFAULT_ESTIMATE_DAYS,
    MAX_ESTIMATE_DAYS,
    MIN_ESTIMATE_DAYS,
    generate_quick_estimate,
)
from app.models import DemandRecord, Product, Warehouse, Workspace


class DemandServiceTest(unittest.TestCase):
    """Unit tests for the quick-estimate generator (CLAUDE.md 5.1).

    These deliberately call the service directly rather than the endpoint so
    a shape regression in the generator is caught independently of the HTTP
    layer — the endpoint tests live in test_api_endpoints.py.
    """

    # A fixed "today" so date-range assertions can't flake as the calendar
    # moves; the generator itself uses date.today() only when none is given.
    TODAY = date(2026, 6, 30)

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        Session = sessionmaker(bind=self.engine)
        self.db = Session()

        workspace = Workspace(name="Test WS", slug="test-ws", is_demo=False)
        self.db.add(workspace)
        self.db.flush()
        self.product = Product(workspace_id=workspace.id, sku="TST-001", name="Test Product", category="Test", unit_cost=1.0, lead_time_days=5)
        self.warehouse = Warehouse(workspace_id=workspace.id, code="WH-TST", name="Test WH", city="Test City", region="Test")
        self.db.add_all([self.product, self.warehouse])
        self.db.flush()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)

    def _rows(self) -> list[DemandRecord]:
        return (
            self.db.query(DemandRecord)
            .filter(DemandRecord.product_id == self.product.id, DemandRecord.warehouse_id == self.warehouse.id)
            .order_by(DemandRecord.record_date.asc())
            .all()
        )

    def _generate(self, avg_units_per_day=40.0, days_back=DEFAULT_ESTIMATE_DAYS):
        return generate_quick_estimate(
            self.db,
            self.product,
            self.warehouse,
            avg_units_per_day=avg_units_per_day,
            days_back=days_back,
            today=self.TODAY,
        )

    def test_generates_the_requested_day_range(self):
        result = self._generate(days_back=45)

        self.assertEqual(result["days_generated"], 45)
        self.assertEqual(result["days_skipped_existing"], 0)
        # Ends yesterday, not today — today isn't a complete day of demand,
        # and forecast_service only reads rows strictly before today anyway.
        self.assertEqual(result["start_date"], (self.TODAY - timedelta(days=45)).isoformat())
        self.assertEqual(result["end_date"], (self.TODAY - timedelta(days=1)).isoformat())
        self.assertTrue(result["is_estimated"])

        rows = self._rows()
        self.assertEqual(len(rows), 45)
        self.assertEqual(rows[0].record_date, self.TODAY - timedelta(days=45))
        self.assertEqual(rows[-1].record_date, self.TODAY - timedelta(days=1))
        # No gaps and no duplicates.
        dates = [row.record_date for row in rows]
        self.assertEqual(dates, sorted(set(dates)))
        self.assertEqual(len(set(dates)), 45)

    def test_every_generated_row_is_flagged_as_estimated(self):
        self._generate()
        rows = self._rows()
        self.assertGreater(len(rows), 0)
        self.assertTrue(all(row.is_estimated for row in rows))

    def test_generated_history_is_not_a_flat_line(self):
        # A single-value series would silently break the forecasting models
        # (zero residual spread, meaningless backtest), so the generator
        # must actually vary day to day.
        self._generate(avg_units_per_day=40.0)
        quantities = {row.demand_qty for row in self._rows()}
        self.assertGreater(len(quantities), 5, "generated demand should vary across days, not repeat one number")

    def test_weekday_pattern_matches_the_seed_generator(self):
        # Same shape as seed.py: weekdays at 1.0x, weekends at 0.6x. The
        # generated series has to show that structure, not just "noise".
        self._generate(avg_units_per_day=40.0)
        weekday_qty, weekend_qty, weekday_days, weekend_days = 0, 0, 0, 0
        for row in self._rows():
            if row.record_date.weekday() < 5:
                weekday_qty += row.demand_qty
                weekday_days += 1
            else:
                weekend_qty += row.demand_qty
                weekend_days += 1

        self.assertGreater(weekday_days, 0)
        self.assertGreater(weekend_days, 0)
        weekday_avg = weekday_qty / weekday_days
        weekend_avg = weekend_qty / weekend_days
        self.assertLess(weekend_avg, weekday_avg * 0.8, "weekend demand should run well below weekday demand")

    def test_average_honors_the_number_the_user_typed(self):
        # The user asks for "about N per day". Weekends run at 0.6x, so the
        # base rate is scaled up by 1/mean_weekday_factor() to keep the
        # overall average near N instead of ~11% under it.
        requested = 40.0
        self._generate(avg_units_per_day=requested)
        avg = sum(row.demand_qty for row in self._rows()) / len(self._rows())
        self.assertAlmostEqual(avg, requested, delta=requested * 0.15)

    def test_same_inputs_reproduce_the_same_history(self):
        # Re-estimating the same pair with the same rate must not reshuffle
        # the numbers a forecast was built on (e.g. when a user clicks the
        # button twice). Same RNG seed => same series.
        first = self._generate(avg_units_per_day=40.0)
        first_rows = [(row.record_date, row.demand_qty) for row in self._rows()]

        # Wipe and regenerate against a fresh connection, same inputs.
        self.db.query(DemandRecord).delete()
        self.db.commit()
        second = self._generate(avg_units_per_day=40.0)
        second_rows = [(row.record_date, row.demand_qty) for row in self._rows()]

        self.assertEqual(first_rows, second_rows)
        self.assertEqual(first, second)

    def test_different_pairs_get_unrelated_series(self):
        other = Product(workspace_id=self.product.workspace_id, sku="TST-002", name="Other", category="Test", unit_cost=1.0, lead_time_days=5)
        self.db.add(other)
        self.db.flush()

        generate_quick_estimate(self.db, self.product, self.warehouse, avg_units_per_day=40.0, today=self.TODAY)
        generate_quick_estimate(self.db, other, self.warehouse, avg_units_per_day=40.0, today=self.TODAY)

        a = [row.demand_qty for row in self._rows()]
        b = [
            row.demand_qty
            for row in self.db.query(DemandRecord).filter(DemandRecord.product_id == other.id).order_by(DemandRecord.record_date.asc()).all()
        ]
        # Same shape (same generator + same rate) but not the identical
        # series — the seed is per-pair.
        self.assertEqual(len(a), len(b))
        self.assertNotEqual(a, b)

    def test_existing_days_are_never_overwritten(self):
        # Real (or seeded) history for the pair must survive a re-estimate —
        # a rough guess never overwrites a measurement.
        kept_date = self.TODAY - timedelta(days=10)
        self.db.add(
            DemandRecord(
                product_id=self.product.id,
                warehouse_id=self.warehouse.id,
                record_date=kept_date,
                demand_qty=999,
                is_estimated=False,
            )
        )
        self.db.commit()

        result = self._generate(days_back=30)
        self.assertEqual(result["days_generated"], 29)  # 30 - the one existing day
        self.assertEqual(result["days_skipped_existing"], 1)

        kept = self.db.query(DemandRecord).filter(DemandRecord.record_date == kept_date).first()
        self.assertEqual(kept.demand_qty, 999)
        self.assertFalse(kept.is_estimated)

    def test_bounds_are_usable_for_the_forecast_backtest(self):
        # The defaults have to be enough for forecast_service's 14-day
        # backtest + trend window; too short and the pair still can't be
        # forecast, which is the whole point of this endpoint.
        self.assertGreaterEqual(DEFAULT_ESTIMATE_DAYS, 30)
        self.assertLessEqual(MIN_ESTIMATE_DAYS, 30)
        self.assertGreater(MAX_ESTIMATE_DAYS, DEFAULT_ESTIMATE_DAYS)

        result = self._generate(days_back=MIN_ESTIMATE_DAYS)
        self.assertEqual(result["days_generated"], MIN_ESTIMATE_DAYS)


if __name__ == "__main__":
    unittest.main()
