import unittest
from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.forecast_service import (
    TREND_WINDOW_DAYS,
    _load_daily_series,
    _moving_average_forecast,
    _recent_level,
    _weekday_factors,
    _weekday_seasonal_forecast,
    generate_all_forecasts,
    generate_forecast_for_pair,
)
from app.models import DemandRecord, Forecast, ForecastPoint, Product, Warehouse, Workspace


class ForecastServiceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        Session = sessionmaker(bind=self.engine)
        self.db = Session()

        self.workspace = Workspace(name="Test WS", slug="test-ws", is_demo=False)
        self.db.add(self.workspace)
        self.db.flush()
        self.warehouse = Warehouse(workspace_id=self.workspace.id, code="WH-TST", name="Test WH", city="Test City", region="Test")
        self.product = Product(workspace_id=self.workspace.id, sku="TST-001", name="Test Product", category="Test", unit_cost=1.0, lead_time_days=5)
        self.db.add_all([self.warehouse, self.product])
        self.db.flush()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)

    def _seed_demand(self, days: int, value_fn):
        """value_fn(day: date, offset: int) -> int, offset counting back from today (0 = yesterday)."""
        today = date.today()
        for offset in range(days, 0, -1):
            day = today - timedelta(days=offset)
            self.db.add(
                DemandRecord(
                    product_id=self.product.id,
                    warehouse_id=self.warehouse.id,
                    record_date=day,
                    demand_qty=value_fn(day, offset),
                )
            )
        self.db.commit()

    # --- data cleaning: gap filling ---

    def test_load_daily_series_fills_gaps_with_zero(self):
        today = date.today()
        # Only seed day -10 and day -1, leaving an 8-day gap.
        self.db.add(DemandRecord(product_id=self.product.id, warehouse_id=self.warehouse.id, record_date=today - timedelta(days=10), demand_qty=5))
        self.db.add(DemandRecord(product_id=self.product.id, warehouse_id=self.warehouse.id, record_date=today - timedelta(days=1), demand_qty=7))
        self.db.commit()

        series = _load_daily_series(self.db, self.product.id, self.warehouse.id)
        self.assertEqual(len(series), 10)  # day -10 through day -1, inclusive, contiguous
        values = {d: v for d, v in series}
        self.assertEqual(values[today - timedelta(days=10)], 5)
        self.assertEqual(values[today - timedelta(days=1)], 7)
        self.assertEqual(values[today - timedelta(days=5)], 0)  # filled gap

    # --- feature engineering: weekday factors ---

    def test_weekday_factors_detect_weekend_dip(self):
        # Weekdays = 10/day, weekends = 2/day -> weekend factor should be well below 1.
        self._seed_demand(60, lambda day, offset: 2 if day.weekday() >= 5 else 10)
        series = _load_daily_series(self.db, self.product.id, self.warehouse.id)
        factors = _weekday_factors(series)

        weekday_avg_factor = sum(factors[d] for d in range(5)) / 5
        weekend_avg_factor = sum(factors[d] for d in (5, 6)) / 2
        self.assertGreater(weekday_avg_factor, weekend_avg_factor)
        self.assertLess(weekend_avg_factor, 0.5)

    # --- baseline models ---

    def test_moving_average_is_flat(self):
        self._seed_demand(30, lambda day, offset: 10)
        series = _load_daily_series(self.db, self.product.id, self.warehouse.id)
        forecast = _moving_average_forecast(series, horizon_days=7, start_date=date.today())
        self.assertEqual(len(forecast), 7)
        self.assertTrue(all(v == forecast[0] for v in forecast))  # genuinely flat
        self.assertAlmostEqual(forecast[0], 10.0, places=1)

    def test_weekday_seasonal_reproduces_known_weekly_pattern(self):
        # Deterministic pattern: weekday=10, weekend=2. A model that has
        # actually learned the weekly cycle should reproduce this shape
        # in its forecast, not just return a flat average.
        self._seed_demand(60, lambda day, offset: 2 if day.weekday() >= 5 else 10)
        series = _load_daily_series(self.db, self.product.id, self.warehouse.id)
        forecast = _weekday_seasonal_forecast(series, horizon_days=14, start_date=date.today())

        for i, value in enumerate(forecast):
            forecast_day = date.today() + timedelta(days=i)
            if forecast_day.weekday() >= 5:
                self.assertLess(value, 5, f"expected a weekend dip on {forecast_day}")
            else:
                self.assertGreater(value, 7, f"expected a weekday level on {forecast_day}")

    def test_recent_level_uses_only_the_tail_window(self):
        # Old data is 100/day, but the last TREND_WINDOW_DAYS are 10/day.
        # The recent level should track the recent regime, not the old one.
        today = date.today()
        for offset in range(60, TREND_WINDOW_DAYS, -1):
            self.db.add(DemandRecord(product_id=self.product.id, warehouse_id=self.warehouse.id, record_date=today - timedelta(days=offset), demand_qty=100))
        for offset in range(TREND_WINDOW_DAYS, 0, -1):
            self.db.add(DemandRecord(product_id=self.product.id, warehouse_id=self.warehouse.id, record_date=today - timedelta(days=offset), demand_qty=10))
        self.db.commit()

        series = _load_daily_series(self.db, self.product.id, self.warehouse.id)
        level = _recent_level(series)
        self.assertAlmostEqual(level, 10.0, delta=1.0)

    # --- evaluation / model selection ---

    def test_weekday_seasonal_wins_backtest_when_pattern_is_real(self):
        # Strong, consistent weekly pattern over enough history that the
        # seasonal model should clearly out-predict a flat moving average
        # on the held-out days.
        self._seed_demand(90, lambda day, offset: 2 if day.weekday() >= 5 else 20)
        product2 = Product(workspace_id=self.workspace.id, sku="TST-002", name="P2", category="Test", unit_cost=1.0, lead_time_days=5)
        self.db.add(product2)
        self.db.flush()

        forecast = generate_forecast_for_pair(self.db, self.product, self.warehouse, horizon_days=14)
        self.assertIsNotNone(forecast)
        self.assertEqual(forecast.method.value, "weekday_seasonal")

    def test_insufficient_history_returns_none(self):
        self._seed_demand(5, lambda day, offset: 10)  # far too little history
        result = generate_forecast_for_pair(self.db, self.product, self.warehouse, horizon_days=14)
        self.assertIsNone(result)

    # --- persistence: no duplication on regeneration ---

    def test_regenerating_replaces_rather_than_duplicates(self):
        self._seed_demand(60, lambda day, offset: 10)
        first = generate_forecast_for_pair(self.db, self.product, self.warehouse, horizon_days=7)
        first_id = first.id

        generate_forecast_for_pair(self.db, self.product, self.warehouse, horizon_days=7)

        all_forecasts = self.db.query(Forecast).filter(
            Forecast.product_id == self.product.id, Forecast.warehouse_id == self.warehouse.id
        ).all()
        # The key guarantee: still exactly one forecast for this pair, not
        # two. (SQLite may or may not reuse the same rowid for the
        # replacement row — that's an implementation detail, not something
        # this test should assert either way.)
        self.assertEqual(len(all_forecasts), 1)

        # Orphaned points from the deleted forecast should be gone too
        # (cascade="all, delete-orphan" on Forecast.points) — and the
        # surviving forecast should have exactly horizon_days points, not
        # double from any leftover rows.
        self.assertEqual(len(all_forecasts[0].points), 7)
        total_points = self.db.query(ForecastPoint).filter(ForecastPoint.forecast_id == first_id).count()
        self.assertLessEqual(total_points, 7)

    def test_forecast_points_count_matches_horizon(self):
        self._seed_demand(60, lambda day, offset: 10)
        forecast = generate_forecast_for_pair(self.db, self.product, self.warehouse, horizon_days=10)
        self.assertEqual(len(forecast.points), 10)
        self.assertEqual([p.day_offset for p in forecast.points], list(range(1, 11)))

    def test_bounds_bracket_the_estimate(self):
        self._seed_demand(60, lambda day, offset: 2 if day.weekday() >= 5 else 10)
        forecast = generate_forecast_for_pair(self.db, self.product, self.warehouse, horizon_days=7)
        for point in forecast.points:
            self.assertLessEqual(point.lower_bound, point.estimated_demand)
            self.assertLessEqual(point.estimated_demand, point.upper_bound)
            self.assertGreaterEqual(point.lower_bound, 0.0)

    def test_generate_all_forecasts_skips_pairs_with_no_demand_history(self):
        # This product has zero DemandRecord rows at all.
        empty_product = Product(workspace_id=self.workspace.id, sku="TST-EMPTY", name="No history", category="Test", unit_cost=1.0, lead_time_days=5)
        self.db.add(empty_product)
        self.db.flush()
        from app.models import Inventory

        self.db.add(Inventory(workspace_id=self.workspace.id, product_id=empty_product.id, warehouse_id=self.warehouse.id, on_hand=10, reserved=0, safety_stock=5, reorder_point=8, incoming_qty=0))
        self._seed_demand(60, lambda day, offset: 10)  # for self.product, not empty_product
        self.db.add(Inventory(workspace_id=self.workspace.id, product_id=self.product.id, warehouse_id=self.warehouse.id, on_hand=10, reserved=0, safety_stock=5, reorder_point=8, incoming_qty=0))
        self.db.commit()

        result = generate_all_forecasts(self.db, self.workspace.id)
        self.assertEqual(result["generated"], 1)
        self.assertEqual(result["skipped_insufficient_history"], 1)


if __name__ == "__main__":
    unittest.main()
