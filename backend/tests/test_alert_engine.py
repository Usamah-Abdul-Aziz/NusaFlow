import unittest
from datetime import date, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.alert_engine import generate_alerts
from app.database import Base
from app.inventory_analysis import clear_cache
from app.models import (
    Alert,
    AlertStatus,
    DemandRecord,
    Inventory,
    Product,
    Shipment,
    ShipmentEvent,
    ShipmentStatus,
    Supplier,
    Warehouse,
    Workspace,
)


class AlertEngineTest(unittest.TestCase):
    def setUp(self):
        # See test_inventory_analysis.py for why this matters: the demand
        # cache in inventory_analysis.py is a module-level dict, and every
        # test file here uses a fresh in-memory SQLite DB where IDs restart
        # at 1 — so a stale cache entry from this file can leak into (or
        # be poisoned by) another test file's product/warehouse of the
        # same id. STOCKOUT_RISK and DEMAND_SPIKE checks both call into
        # avg_daily_demand(), so this file is one of the ones that needs it.
        clear_cache()

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
        clear_cache()

    def _make_product(self, **kwargs) -> Product:
        defaults = dict(workspace_id=self.workspace.id, sku="TST-001", name="Test Product", category="Test", unit_cost=1.0, lead_time_days=5)
        defaults.update(kwargs)
        product = Product(**defaults)
        self.db.add(product)
        self.db.flush()
        return product

    def _make_inventory(self, product: Product, **kwargs) -> Inventory:
        defaults = dict(
            workspace_id=self.workspace.id,
            product_id=product.id,
            warehouse_id=self.warehouse.id,
            on_hand=100,
            reserved=0,
            safety_stock=20,
            reorder_point=35,
            incoming_qty=0,
        )
        defaults.update(kwargs)
        inv = Inventory(**defaults)
        self.db.add(inv)
        self.db.flush()
        return inv

    def _add_demand(self, product: Product, days_ago_start: int, days_ago_end: int, qty: int):
        """Insert flat demand_qty for every day in [days_ago_end, days_ago_start) counting back from today."""
        today = date.today()
        for offset in range(days_ago_end, days_ago_start):
            self.db.add(
                DemandRecord(
                    product_id=product.id,
                    warehouse_id=self.warehouse.id,
                    record_date=today - timedelta(days=offset),
                    demand_qty=qty,
                )
            )
        self.db.flush()

    # --- LOW_STOCK / CRITICAL_STOCK ---

    def test_critical_stock_when_at_or_below_safety_stock(self):
        product = self._make_product()
        self._make_inventory(product, on_hand=15, safety_stock=20, reorder_point=35)
        generate_alerts(self.db, self.workspace.id)
        alerts = self.db.query(Alert).all()
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].alert_type.value, "CRITICAL_STOCK")

    def test_low_stock_when_between_safety_stock_and_reorder_point(self):
        product = self._make_product()
        self._make_inventory(product, on_hand=30, safety_stock=20, reorder_point=35)
        generate_alerts(self.db, self.workspace.id)
        alerts = self.db.query(Alert).all()
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].alert_type.value, "LOW_STOCK")

    def test_no_stock_alert_when_healthy(self):
        product = self._make_product()
        self._make_inventory(product, on_hand=500, safety_stock=20, reorder_point=35)
        generate_alerts(self.db, self.workspace.id)
        stock_alerts = [a for a in self.db.query(Alert).all() if "STOCK" in a.alert_type.value]
        self.assertEqual(stock_alerts, [])

    # --- SHIPMENT_DELAY ---

    def test_shipment_delay_alert_only_for_active_overdue_shipments(self):
        product = self._make_product()
        self._make_inventory(product, on_hand=500, safety_stock=20, reorder_point=35)  # keep stock alerts out of the way

        overdue = Shipment(
            workspace_id=self.workspace.id,
            shipment_number="SH-OVERDUE",
            product_id=product.id,
            warehouse_id=self.warehouse.id,
            supplier_id=self.supplier.id,
            quantity=10,
            status=ShipmentStatus.IN_TRANSIT,
            eta_date=date.today() - timedelta(days=6),
        )
        on_time = Shipment(
            workspace_id=self.workspace.id,
            shipment_number="SH-ONTIME",
            product_id=product.id,
            warehouse_id=self.warehouse.id,
            supplier_id=self.supplier.id,
            quantity=10,
            status=ShipmentStatus.IN_TRANSIT,
            eta_date=date.today() + timedelta(days=3),
        )
        self.db.add_all([overdue, on_time])
        self.db.commit()

        generate_alerts(self.db, self.workspace.id)
        alerts = self.db.query(Alert).filter(Alert.alert_type == "SHIPMENT_DELAY").all()
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].related_entity_label, "SH-OVERDUE")
        self.assertEqual(alerts[0].severity.value, "CRITICAL")  # 6 days >= SHIPMENT_DELAY_CRITICAL_DAYS (5)

    # --- SUPPLIER_DELAY ---

    def test_supplier_delay_needs_minimum_sample_size(self):
        product = self._make_product()
        self._make_inventory(product, on_hand=500, safety_stock=20, reorder_point=35)
        # Only 2 delivered shipments, both late — below SUPPLIER_MIN_SAMPLE (3), should NOT alert.
        for i in range(2):
            self.db.add(
                Shipment(
                    workspace_id=self.workspace.id,
                    shipment_number=f"SH-LATE-{i}",
                    product_id=product.id,
                    warehouse_id=self.warehouse.id,
                    supplier_id=self.supplier.id,
                    quantity=10,
                    status=ShipmentStatus.DELIVERED,
                    eta_date=date.today() - timedelta(days=10),
                    actual_delivery_date=date.today() - timedelta(days=5),
                )
            )
        self.db.commit()
        generate_alerts(self.db, self.workspace.id)
        self.assertEqual(self.db.query(Alert).filter(Alert.alert_type == "SUPPLIER_DELAY").count(), 0)

    def test_supplier_delay_fires_above_threshold_with_enough_samples(self):
        product = self._make_product()
        self._make_inventory(product, on_hand=500, safety_stock=20, reorder_point=35)
        # 4 delivered, 3 late (75%) -> well above both thresholds.
        for i in range(4):
            late = i < 3
            self.db.add(
                Shipment(
                    workspace_id=self.workspace.id,
                    shipment_number=f"SH-{i}",
                    product_id=product.id,
                    warehouse_id=self.warehouse.id,
                    supplier_id=self.supplier.id,
                    quantity=10,
                    status=ShipmentStatus.DELIVERED,
                    eta_date=date.today() - timedelta(days=10),
                    actual_delivery_date=date.today() - timedelta(days=5 if late else 10),
                )
            )
        self.db.commit()
        generate_alerts(self.db, self.workspace.id)
        alerts = self.db.query(Alert).filter(Alert.alert_type == "SUPPLIER_DELAY").all()
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].severity.value, "CRITICAL")  # 75% >= SUPPLIER_LATE_RATE_CRITICAL (50%)

    # --- DEMAND_SPIKE ---

    def test_demand_spike_detected_from_recent_vs_baseline(self):
        product = self._make_product()
        self._make_inventory(product, on_hand=500, safety_stock=20, reorder_point=35)
        self._add_demand(product, days_ago_start=28, days_ago_end=7, qty=5)  # baseline: 5/day
        self._add_demand(product, days_ago_start=7, days_ago_end=0, qty=15)  # recent: 15/day (3x)
        generate_alerts(self.db, self.workspace.id)
        alerts = self.db.query(Alert).filter(Alert.alert_type == "DEMAND_SPIKE").all()
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].severity.value, "CRITICAL")  # 3x >= DEMAND_SPIKE_CRITICAL_MULTIPLIER (2x)

    def test_no_demand_spike_when_flat(self):
        product = self._make_product()
        self._make_inventory(product, on_hand=500, safety_stock=20, reorder_point=35)
        self._add_demand(product, days_ago_start=28, days_ago_end=0, qty=5)  # flat 5/day throughout
        generate_alerts(self.db, self.workspace.id)
        self.assertEqual(self.db.query(Alert).filter(Alert.alert_type == "DEMAND_SPIKE").count(), 0)

    # --- reconciliation: dedupe / refresh / auto-resolve ---

    def test_running_twice_does_not_duplicate_alerts(self):
        product = self._make_product()
        self._make_inventory(product, on_hand=10, safety_stock=20, reorder_point=35)
        generate_alerts(self.db, self.workspace.id)
        first_count = self.db.query(Alert).count()
        result = generate_alerts(self.db, self.workspace.id)
        second_count = self.db.query(Alert).count()

        self.assertEqual(first_count, second_count)
        self.assertEqual(result["created"], 0)

    def test_condition_clearing_auto_resolves_alert(self):
        product = self._make_product()
        inv = self._make_inventory(product, on_hand=10, safety_stock=20, reorder_point=35)
        generate_alerts(self.db, self.workspace.id)
        self.assertEqual(
            self.db.query(Alert).filter(Alert.status == AlertStatus.OPEN).count(), 1
        )

        inv.on_hand = 500  # restock above reorder point
        self.db.commit()
        result = generate_alerts(self.db, self.workspace.id)

        self.assertEqual(result["resolved"], 1)
        alert = self.db.query(Alert).first()
        self.assertEqual(alert.status, AlertStatus.RESOLVED)
        self.assertIsNotNone(alert.resolved_at)

    def test_manually_resolved_alert_is_not_reopened_by_engine(self):
        product = self._make_product()
        self._make_inventory(product, on_hand=10, safety_stock=20, reorder_point=35)
        generate_alerts(self.db, self.workspace.id)
        alert = self.db.query(Alert).first()
        alert.status = AlertStatus.RESOLVED
        self.db.commit()

        # Condition is still true, but the engine should open a NEW alert
        # rather than silently leaving the human-resolved one untouched
        # forever while the underlying problem persists.
        generate_alerts(self.db, self.workspace.id)
        all_alerts = self.db.query(Alert).all()
        self.assertEqual(len(all_alerts), 2)
        statuses = sorted(a.status.value for a in all_alerts)
        self.assertEqual(statuses, ["OPEN", "RESOLVED"])


if __name__ == "__main__":
    unittest.main()
