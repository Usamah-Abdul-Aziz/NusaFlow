import unittest
from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import (
    DemandRecord,
    Forecast,
    ForecastPoint,
    Inventory,
    Product,
    Shipment,
    ShipmentStatus,
    SimulationResult,
    Supplier,
    Warehouse,
    Workspace,
)
from app.simulation_service import ScenarioParams, compute_comparison, create_and_run_scenario, rerun_scenario


class SimulationServiceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        Session = sessionmaker(bind=self.engine)
        self.db = Session()

        self.workspace = Workspace(name="Test WS", slug="test-ws", is_demo=False)
        self.db.add(self.workspace)
        self.db.flush()
        self.warehouse = Warehouse(workspace_id=self.workspace.id, code="WH-TST", name="Test WH", city="Test City", region="Test")
        self.supplier = Supplier(workspace_id=self.workspace.id, name="Test Supplier", lead_time_days=5, delay_rate=0.1, reliability_score=0.9)
        self.db.add_all([self.warehouse, self.supplier])
        self.db.flush()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)

    def _make_product_with_data(self, lead_time_days=5, on_hand=50, safety_stock=20, incoming_qty=0, daily_demand=5.0, unit_cost=10.0):
        product = Product(workspace_id=self.workspace.id, sku="TST-001", name="Test Product", category="Test", unit_cost=unit_cost, lead_time_days=lead_time_days)
        self.db.add(product)
        self.db.flush()

        self.db.add(
            Inventory(
                workspace_id=self.workspace.id, product_id=product.id, warehouse_id=self.warehouse.id,
                on_hand=on_hand, reserved=0, safety_stock=safety_stock, reorder_point=safety_stock + 10, incoming_qty=incoming_qty,
            )
        )
        today = date.today()
        for offset in range(30, 0, -1):
            self.db.add(
                DemandRecord(product_id=product.id, warehouse_id=self.warehouse.id, record_date=today - timedelta(days=offset), demand_qty=daily_demand)
            )
        forecast = Forecast(
            workspace_id=self.workspace.id, product_id=product.id, warehouse_id=self.warehouse.id, method="moving_average",
            horizon_days=30, mae=1.0, mape=10.0, residual_std=1.0,
        )
        self.db.add(forecast)
        self.db.flush()
        for i in range(1, 31):
            self.db.add(
                ForecastPoint(
                    forecast_id=forecast.id, forecast_date=today + timedelta(days=i - 1),
                    day_offset=i, estimated_demand=daily_demand, lower_bound=daily_demand - 1, upper_bound=daily_demand + 1,
                )
            )
        self.db.commit()
        return product

    # --- baseline sanity ---

    def test_baseline_equals_baseline_when_params_are_all_zero(self):
        self._make_product_with_data()
        comparison = compute_comparison(self.db, self.workspace.id, ScenarioParams())
        self.assertEqual(comparison["baseline"], comparison["simulated"])
        self.assertTrue(all(v == 0 for v in comparison["delta"].values()))

    # --- directional correctness: a worse scenario should never look better ---

    def test_increased_demand_and_delay_never_improves_metrics(self):
        self._make_product_with_data()
        params = ScenarioParams(demand_change_pct=20, lead_time_delta_days=3, shipment_delay_delta_days=2)
        comparison = compute_comparison(self.db, self.workspace.id, params)

        self.assertGreaterEqual(comparison["simulated"]["stockout_risk_count"], comparison["baseline"]["stockout_risk_count"])
        self.assertGreaterEqual(comparison["simulated"]["late_shipments_count"], comparison["baseline"]["late_shipments_count"])
        self.assertLessEqual(comparison["simulated"]["service_level_pct"], comparison["baseline"]["service_level_pct"])
        self.assertGreaterEqual(comparison["simulated"]["inventory_cost"], comparison["baseline"]["inventory_cost"])
        self.assertGreaterEqual(comparison["simulated"]["replenishment_requirement"], comparison["baseline"]["replenishment_requirement"])

    def test_more_safety_stock_increases_replenishment_requirement(self):
        self._make_product_with_data(on_hand=10)  # understocked, so safety stock actually binds
        low = compute_comparison(self.db, self.workspace.id, ScenarioParams(safety_stock_change_pct=0))
        high = compute_comparison(self.db, self.workspace.id, ScenarioParams(safety_stock_change_pct=50))
        self.assertGreaterEqual(high["simulated"]["replenishment_requirement"], low["simulated"]["replenishment_requirement"])

    # --- late shipments respond to shipment_delay_delta_days ---

    def test_shipment_delay_delta_can_push_on_time_shipment_into_late(self):
        product = self._make_product_with_data()
        # eta is 1 day in the future -> currently on time (0 real delay).
        shipment = Shipment(
            workspace_id=self.workspace.id,
            shipment_number="SH-1", product_id=product.id, warehouse_id=self.warehouse.id, supplier_id=self.supplier.id,
            quantity=10, status=ShipmentStatus.IN_TRANSIT, eta_date=date.today() + timedelta(days=1),
        )
        self.db.add(shipment)
        self.db.commit()

        no_delta = compute_comparison(self.db, self.workspace.id, ScenarioParams())
        with_delta = compute_comparison(self.db, self.workspace.id, ScenarioParams(shipment_delay_delta_days=5))

        self.assertEqual(no_delta["baseline"]["late_shipments_count"], 0)
        self.assertEqual(with_delta["simulated"]["late_shipments_count"], 1)

    def test_delivered_and_cancelled_shipments_excluded_from_late_count(self):
        product = self._make_product_with_data()
        delivered = Shipment(
            workspace_id=self.workspace.id,
            shipment_number="SH-DONE", product_id=product.id, warehouse_id=self.warehouse.id, supplier_id=self.supplier.id,
            quantity=10, status=ShipmentStatus.DELIVERED, eta_date=date.today() - timedelta(days=10),
            actual_delivery_date=date.today() - timedelta(days=5),  # was late historically
        )
        self.db.add(delivered)
        self.db.commit()

        comparison = compute_comparison(self.db, self.workspace.id, ScenarioParams(shipment_delay_delta_days=10))
        self.assertEqual(comparison["simulated"]["late_shipments_count"], 0)

    # --- does not touch real operational data ---

    def test_does_not_mutate_real_inventory_or_shipment_rows(self):
        product = self._make_product_with_data(on_hand=50, safety_stock=20, incoming_qty=0)
        inv_before = self.db.query(Inventory).filter(Inventory.product_id == product.id).first()
        on_hand_before, safety_stock_before = inv_before.on_hand, inv_before.safety_stock

        compute_comparison(self.db, self.workspace.id, ScenarioParams(demand_change_pct=50, safety_stock_change_pct=50, lead_time_delta_days=10))

        inv_after = self.db.query(Inventory).filter(Inventory.product_id == product.id).first()
        self.assertEqual(inv_after.on_hand, on_hand_before)
        self.assertEqual(inv_after.safety_stock, safety_stock_before)

    # --- persistence ---

    def test_create_and_run_scenario_persists_both_results(self):
        self._make_product_with_data()
        scenario = create_and_run_scenario(self.db, self.workspace.id, "Test scenario", ScenarioParams(demand_change_pct=20))

        results = self.db.query(SimulationResult).filter(SimulationResult.scenario_id == scenario.id).all()
        self.assertEqual(len(results), 2)
        self.assertEqual({r.is_baseline for r in results}, {True, False})

    def test_rerun_adds_a_fresh_result_pair(self):
        self._make_product_with_data()
        scenario = create_and_run_scenario(self.db, self.workspace.id, "Test scenario", ScenarioParams(demand_change_pct=20))
        rerun_scenario(self.db, scenario)

        results = self.db.query(SimulationResult).filter(SimulationResult.scenario_id == scenario.id).all()
        self.assertEqual(len(results), 4)  # 2 from create, 2 more from rerun


if __name__ == "__main__":
    unittest.main()
