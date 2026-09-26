import unittest
from datetime import date, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Product, Shipment, ShipmentEvent, Supplier, Warehouse, Workspace
from app.shipment_service import (
    ShipmentAlreadyTerminalError,
    _next_shipment_number,
    advance_shipment,
    compute_delay_days,
    create_shipment,
    effective_status,
    get_events,
)


class ShipmentServiceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        Session = sessionmaker(bind=self.engine)
        self.db = Session()

        self.workspace = Workspace(name="Test WS", slug="test-ws", is_demo=False)
        self.db.add(self.workspace)
        self.db.flush()
        self.product = Product(workspace_id=self.workspace.id, sku="TST-001", name="Test Product", category="Test", unit_cost=1.0, lead_time_days=5)
        self.warehouse = Warehouse(workspace_id=self.workspace.id, code="WH-TST", name="Test WH", city="Test City", region="Test")
        self.supplier = Supplier(workspace_id=self.workspace.id, name="Test Supplier", lead_time_days=5, delay_rate=0.1, reliability_score=0.9)
        self.db.add_all([self.product, self.warehouse, self.supplier])
        self.db.flush()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)

    def _make_shipment(self, **kwargs) -> Shipment:
        defaults = dict(
            workspace_id=self.workspace.id,
            shipment_number="SH-TEST",
            product_id=self.product.id,
            warehouse_id=self.warehouse.id,
            supplier_id=self.supplier.id,
            quantity=10,
            eta_date=date.today(),
            created_at=datetime.utcnow(),
        )
        defaults.update(kwargs)
        shipment = Shipment(**defaults)
        self.db.add(shipment)
        self.db.flush()
        return shipment

    # --- effective_status / compute_delay_days ---

    def test_in_transit_not_yet_due_stays_in_transit(self):
        shipment = self._make_shipment(status="in_transit", eta_date=date.today() + timedelta(days=3))
        self.assertEqual(effective_status(shipment), "in_transit")
        self.assertEqual(compute_delay_days(shipment), 0)

    def test_in_transit_past_eta_reports_delayed_without_manual_update(self):
        # Nobody has "advanced" this shipment — it just quietly went overdue.
        shipment = self._make_shipment(status="in_transit", eta_date=date.today() - timedelta(days=4))
        self.assertEqual(effective_status(shipment), "delayed")
        self.assertEqual(compute_delay_days(shipment), 4)

    def test_delivered_on_time_has_zero_delay(self):
        shipment = self._make_shipment(
            status="delivered",
            eta_date=date.today() - timedelta(days=10),
            actual_delivery_date=date.today() - timedelta(days=11),  # arrived a day early
        )
        self.assertEqual(effective_status(shipment), "delivered")
        self.assertEqual(compute_delay_days(shipment), 0)

    def test_delivered_late_has_positive_delay(self):
        shipment = self._make_shipment(
            status="delivered",
            eta_date=date.today() - timedelta(days=10),
            actual_delivery_date=date.today() - timedelta(days=7),  # 3 days late
        )
        self.assertEqual(compute_delay_days(shipment), 3)

    def test_pending_never_reports_delay(self):
        shipment = self._make_shipment(status="pending", eta_date=date.today() - timedelta(days=2))
        # Hasn't departed yet, so "delayed" framing doesn't apply.
        self.assertEqual(effective_status(shipment), "pending")
        self.assertEqual(compute_delay_days(shipment), 0)

    def test_cancelled_always_zero_delay(self):
        shipment = self._make_shipment(status="cancelled", eta_date=date.today() - timedelta(days=30))
        self.assertEqual(compute_delay_days(shipment), 0)

    # --- create_shipment (manual shipments, CLAUDE.md 5.2) ---

    def test_create_shipment_starts_pending_with_created_event(self):
        shipment = create_shipment(
            self.db,
            self.workspace.id,
            product=self.product,
            warehouse=self.warehouse,
            supplier=self.supplier,
            quantity=25,
            eta_date=date.today() + timedelta(days=6),
        )

        # Manual shipments get their own SH-M#### range, so a brand-new
        # workspace starts counting from 1 and can't collide with a seeded
        # SH-1#### number.
        self.assertEqual(shipment.shipment_number, "SH-M0001")
        self.assertEqual(shipment.status, "pending")
        self.assertEqual(shipment.delay_days, 0)
        self.assertEqual(shipment.quantity, 25)
        self.assertEqual(effective_status(shipment), "pending")

        events = get_events(self.db, shipment.id)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "Shipment Created")

    def test_create_shipment_can_be_advanced_like_a_seeded_one(self):
        # The whole point of 5.2: a manually created shipment must behave
        # identically to a seeded one under the existing "Simulate next
        # step" flow — including taking its FIRST step, which is only
        # possible because create_shipment writes "Shipment Created".
        shipment = create_shipment(
            self.db,
            self.workspace.id,
            product=self.product,
            warehouse=self.warehouse,
            supplier=self.supplier,
            quantity=10,
            eta_date=date.today() + timedelta(days=6),
        )

        advance_shipment(self.db, shipment)  # Created -> Departed
        self.assertEqual(shipment.status, "in_transit")
        self.assertEqual(len(get_events(self.db, shipment.id)), 2)

        advance_shipment(self.db, shipment)  # -> Checkpoint (still before eta)
        advance_shipment(self.db, shipment)  # -> Delivered
        self.assertEqual(shipment.status, "delivered")
        self.assertEqual(shipment.delay_days, 0)

    def test_create_shipment_in_transit_status(self):
        shipment = create_shipment(
            self.db,
            self.workspace.id,
            product=self.product,
            warehouse=self.warehouse,
            supplier=self.supplier,
            quantity=4,
            eta_date=date.today() + timedelta(days=2),
            status="in_transit",
        )
        self.assertEqual(shipment.status, "in_transit")
        self.assertEqual(effective_status(shipment), "in_transit")

    def test_manual_shipment_numbers_are_unique_and_monotonic(self):
        a = create_shipment(self.db, self.workspace.id, product=self.product, warehouse=self.warehouse, supplier=self.supplier, quantity=1, eta_date=date.today())
        b = create_shipment(self.db, self.workspace.id, product=self.product, warehouse=self.warehouse, supplier=self.supplier, quantity=1, eta_date=date.today())
        c = create_shipment(self.db, self.workspace.id, product=self.product, warehouse=self.warehouse, supplier=self.supplier, quantity=1, eta_date=date.today())

        numbers = [a.shipment_number, b.shipment_number, c.shipment_number]
        self.assertEqual(numbers, ["SH-M0001", "SH-M0002", "SH-M0003"])
        self.assertEqual(len(set(numbers)), 3)

    def test_manual_numbers_ignore_seeded_numbering_range(self):
        # A seeded shipment already owns SH-1000; the manual counter must
        # not start after it (that's how a collision would sneak in).
        self._make_shipment(shipment_number="SH-1000")
        self.db.commit()

        self.assertEqual(_next_shipment_number(self.db, self.workspace.id), "SH-M0001")

    def test_manual_number_uses_surviving_max_not_row_count(self):
        # max+1, not count+1: a gap in the numbering (rows deleted directly
        # in the DB, or a number reserved) must not make the generator hand
        # out a number that already belongs to a surviving row.
        self._make_shipment(shipment_number="SH-M0040")
        self.db.commit()

        self.assertEqual(_next_shipment_number(self.db, self.workspace.id), "SH-M0041")

    # --- advance_shipment lifecycle ---

    def test_advance_full_lifecycle_on_time(self):
        shipment = self._make_shipment(status="pending", eta_date=date.today() + timedelta(days=5))
        self.db.add(ShipmentEvent(shipment_id=shipment.id, event_type="Shipment Created", event_time=datetime.utcnow()))
        self.db.commit()

        advance_shipment(self.db, shipment)  # -> Departed
        self.assertEqual(shipment.status, "in_transit")

        advance_shipment(self.db, shipment)  # -> Checkpoint (still before eta)
        self.assertEqual(shipment.status, "in_transit")

        advance_shipment(self.db, shipment)  # -> Delivered
        self.assertEqual(shipment.status, "delivered")
        self.assertEqual(shipment.delay_days, 0)

        with self.assertRaises(ShipmentAlreadyTerminalError):
            advance_shipment(self.db, shipment)

    def test_advance_detects_delay_when_past_eta(self):
        shipment = self._make_shipment(status="pending", eta_date=date.today() - timedelta(days=2))
        self.db.add(ShipmentEvent(shipment_id=shipment.id, event_type="Shipment Created", event_time=datetime.utcnow()))
        self.db.commit()

        advance_shipment(self.db, shipment)  # -> Departed
        event = advance_shipment(self.db, shipment)  # already past eta -> Delay Detected, not Checkpoint
        self.assertEqual(event.event_type, "Delay Detected")
        self.assertEqual(shipment.status, "delayed")

        advance_shipment(self.db, shipment)  # -> Delivered, late
        self.assertEqual(shipment.status, "delivered")
        self.assertGreater(shipment.delay_days, 0)

    def test_events_are_returned_in_chronological_order(self):
        shipment = self._make_shipment(status="pending", eta_date=date.today() + timedelta(days=5))
        self.db.add(ShipmentEvent(shipment_id=shipment.id, event_type="Shipment Created", event_time=datetime.utcnow()))
        self.db.commit()
        advance_shipment(self.db, shipment)
        advance_shipment(self.db, shipment)

        events = get_events(self.db, shipment.id)
        event_times = [e.event_time for e in events]
        self.assertEqual(event_times, sorted(event_times))


if __name__ == "__main__":
    unittest.main()
