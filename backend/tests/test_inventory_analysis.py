import unittest
from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Product, Warehouse, Inventory, DemandRecord, Workspace
from app.inventory_analysis import avg_daily_demand, analyze_inventory_item, clear_cache


class InventoryAnalysisTest(unittest.TestCase):
    def setUp(self):
        # The demand cache in inventory_analysis.py is a module-level dict,
        # keyed by (product_id, warehouse_id, window_days, start_date). Each
        # test here uses a fresh in-memory SQLite DB where autoincrement IDs
        # restart at 1 — so without clearing the cache, a stale entry left
        # behind by another test file (e.g. test_alert_engine.py, which also
        # creates a product/warehouse that land on id=1) can leak in and
        # make this test read someone else's cached average. Clearing on
        # both setUp and tearDown keeps this test isolated either way.
        clear_cache()

        # in-memory SQLite for fast tests
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        Session = sessionmaker(bind=self.engine)
        self.db = Session()

        # create workspace, product, and warehouse
        self.workspace = Workspace(name="Test WS", slug="test-ws", is_demo=False)
        self.db.add(self.workspace)
        self.db.flush()
        self.product = Product(workspace_id=self.workspace.id, sku="TST-001", name="Test Product", category="Test", unit_cost=1.0, lead_time_days=5)
        self.warehouse = Warehouse(workspace_id=self.workspace.id, code="WH-TST", name="Test WH", city="Test City", region="Test")
        self.db.add(self.product)
        self.db.add(self.warehouse)
        self.db.flush()

        # inventory with 100 units on hand
        self.inv = Inventory(workspace_id=self.workspace.id, product_id=self.product.id, warehouse_id=self.warehouse.id, on_hand=100, reserved=0, safety_stock=10, reorder_point=20, incoming_qty=0)
        self.db.add(self.inv)
        self.db.flush()

        # seed 30 days of demand: 2 units per day
        base = date.today() - timedelta(days=30)
        for i in range(30):
            self.db.add(DemandRecord(product_id=self.product.id, warehouse_id=self.warehouse.id, record_date=base + timedelta(days=i), demand_qty=2))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=self.engine)
        clear_cache()

    def test_avg_daily_demand(self):
        avg = avg_daily_demand(self.db, self.product.id, self.warehouse.id, window_days=30)
        # 30 days * 2 units = 60 total -> avg = 2.0
        self.assertAlmostEqual(avg, 2.0, places=4)

    def test_analyze_inventory_item_days_and_risk(self):
        res = analyze_inventory_item(self.db, self.inv, window_days=30)
        # days_of_inventory = 100 / 2 = 50
        self.assertIn("days_of_inventory", res)
        self.assertAlmostEqual(res["days_of_inventory"], 50.0, places=2)
        # safety_days = round(10 / 2) = 5, lead_time=5 -> threshold=10; days_of_inventory 50 > 10 -> no risk
        self.assertFalse(res["stockout_risk"]) 


if __name__ == '__main__':
    unittest.main()
