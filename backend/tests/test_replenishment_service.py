import unittest
from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Forecast, ForecastPoint, Inventory, Product, ReplenishmentRecommendation, Warehouse, Workspace
from app.replenishment_service import generate_all_recommendations, generate_recommendation_for_pair


class ReplenishmentServiceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        Session = sessionmaker(bind=self.engine)
        self.db = Session()

        self.workspace = Workspace(name="Test WS", slug="test-ws", is_demo=False)
        self.db.add(self.workspace)
        self.db.flush()
        self.warehouse = Warehouse(workspace_id=self.workspace.id, code="WH-TST", name="Test WH", city="Test City", region="Test")
        self.db.add(self.warehouse)
        self.db.flush()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)

    def _make_product(self, lead_time_days: int) -> Product:
        product = Product(workspace_id=self.workspace.id, sku="TST-001", name="Test Product", category="Test", unit_cost=1.0, lead_time_days=lead_time_days)
        self.db.add(product)
        self.db.flush()
        return product

    def _make_inventory(self, product: Product, on_hand: int, safety_stock: int, incoming_qty: int) -> Inventory:
        inv = Inventory(
            workspace_id=self.workspace.id,
            product_id=product.id,
            warehouse_id=self.warehouse.id,
            on_hand=on_hand,
            reserved=0,
            safety_stock=safety_stock,
            reorder_point=safety_stock + 10,
            incoming_qty=incoming_qty,
        )
        self.db.add(inv)
        self.db.flush()
        return inv

    def _make_forecast(self, product: Product, daily_points: list[float]) -> Forecast:
        """A forecast whose points sum to a controlled total, so tests can
        target an exact Forecast Demand rather than depending on the real
        (randomized) forecasting pipeline from Phase 5.
        """
        forecast = Forecast(
            workspace_id=self.workspace.id,
            product_id=product.id,
            warehouse_id=self.warehouse.id,
            method="moving_average",
            horizon_days=len(daily_points),
            mae=1.0,
            mape=10.0,
            residual_std=1.0,
        )
        self.db.add(forecast)
        self.db.flush()
        today = date.today()
        for i, value in enumerate(daily_points, start=1):
            self.db.add(
                ForecastPoint(
                    forecast_id=forecast.id,
                    forecast_date=today + timedelta(days=i - 1),
                    day_offset=i,
                    estimated_demand=value,
                    lower_bound=max(0.0, value - 1),
                    upper_bound=value + 1,
                )
            )
        self.db.commit()
        self.db.refresh(forecast)
        return forecast

    # --- matches the literal AGENTS.md example ---

    def test_matches_agents_md_worked_example(self):
        # AGENTS.md section 11:
        #   Current Stock 85, Incoming Stock 20, Forecast Demand 180, Safety Stock 50
        #   Recommended Order = max(180 + 50 - 85 - 20, 0) = 125
        product = self._make_product(lead_time_days=10)
        inventory = self._make_inventory(product, on_hand=85, safety_stock=50, incoming_qty=20)
        # 10 points of 18 = 180 total forecast demand over the 10-day lead time.
        self._make_forecast(product, [18.0] * 10)

        rec = generate_recommendation_for_pair(self.db, product, self.warehouse, inventory)

        self.assertIsNotNone(rec)
        self.assertAlmostEqual(rec.forecast_demand, 180.0, places=1)
        self.assertAlmostEqual(rec.recommended_quantity, 125.0, places=1)
        self.assertIn("125.0", rec.explanation)

    # --- floor at zero ---

    def test_recommended_quantity_floors_at_zero_when_overstocked(self):
        product = self._make_product(lead_time_days=5)
        # Way more on hand than forecast demand + safety stock could ever need.
        inventory = self._make_inventory(product, on_hand=1000, safety_stock=20, incoming_qty=0)
        self._make_forecast(product, [10.0] * 30)

        rec = generate_recommendation_for_pair(self.db, product, self.warehouse, inventory)
        self.assertEqual(rec.recommended_quantity, 0.0)

    # --- only sums the lead-time window, not the whole forecast ---

    def test_only_sums_points_within_lead_time(self):
        product = self._make_product(lead_time_days=5)
        inventory = self._make_inventory(product, on_hand=0, safety_stock=0, incoming_qty=0)
        # 30 days of forecast, all at 10/day — but lead time is only 5 days,
        # so Forecast Demand should be 5*10=50, NOT 30*10=300.
        self._make_forecast(product, [10.0] * 30)

        rec = generate_recommendation_for_pair(self.db, product, self.warehouse, inventory)
        self.assertAlmostEqual(rec.forecast_demand, 50.0, places=1)
        self.assertAlmostEqual(rec.recommended_quantity, 50.0, places=1)

    # --- incoming stock reduces the recommendation ---

    def test_incoming_stock_reduces_recommendation(self):
        product = self._make_product(lead_time_days=5)
        inventory_no_incoming = self._make_inventory(product, on_hand=0, safety_stock=0, incoming_qty=0)
        self._make_forecast(product, [10.0] * 30)
        rec_no_incoming = generate_recommendation_for_pair(self.db, product, self.warehouse, inventory_no_incoming)

        inventory_no_incoming.incoming_qty = 20
        self.db.commit()
        rec_with_incoming = generate_recommendation_for_pair(self.db, product, self.warehouse, inventory_no_incoming)

        self.assertEqual(rec_with_incoming.recommended_quantity, rec_no_incoming.recommended_quantity - 20)

    # --- skip when no forecast exists ---

    def test_skips_pair_with_no_forecast(self):
        product = self._make_product(lead_time_days=5)
        inventory = self._make_inventory(product, on_hand=10, safety_stock=20, incoming_qty=0)
        # No _make_forecast() call — this pair has no Phase 5 forecast yet.

        rec = generate_recommendation_for_pair(self.db, product, self.warehouse, inventory)
        self.assertIsNone(rec)

    def test_generate_all_recommendations_counts_skipped(self):
        product_with_forecast = self._make_product(lead_time_days=5)
        inv1 = self._make_inventory(product_with_forecast, on_hand=10, safety_stock=20, incoming_qty=0)
        self._make_forecast(product_with_forecast, [5.0] * 10)

        product_without_forecast = Product(workspace_id=self.workspace.id, sku="TST-002", name="No Forecast", category="Test", unit_cost=1.0, lead_time_days=5)
        self.db.add(product_without_forecast)
        self.db.flush()
        self.db.add(
            Inventory(
                workspace_id=self.workspace.id,
                product_id=product_without_forecast.id,
                warehouse_id=self.warehouse.id,
                on_hand=10, reserved=0, safety_stock=20, reorder_point=30, incoming_qty=0,
            )
        )
        self.db.commit()

        result = generate_all_recommendations(self.db, self.workspace.id)
        self.assertEqual(result["generated"], 1)
        self.assertEqual(result["skipped_no_forecast"], 1)

    # --- regenerating replaces rather than duplicates ---

    def test_regenerating_replaces_rather_than_duplicates(self):
        product = self._make_product(lead_time_days=5)
        inventory = self._make_inventory(product, on_hand=10, safety_stock=20, incoming_qty=0)
        self._make_forecast(product, [5.0] * 10)

        generate_recommendation_for_pair(self.db, product, self.warehouse, inventory)
        generate_recommendation_for_pair(self.db, product, self.warehouse, inventory)

        all_recs = (
            self.db.query(ReplenishmentRecommendation)
            .filter(
                ReplenishmentRecommendation.product_id == product.id,
                ReplenishmentRecommendation.warehouse_id == self.warehouse.id,
            )
            .all()
        )
        self.assertEqual(len(all_recs), 1)


if __name__ == "__main__":
    unittest.main()
