import unittest
from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.alert_engine import generate_alerts
from app.auth import create_access_token
from app.database import Base, get_db
from app.forecast_service import generate_all_forecasts
from app.inventory_analysis import clear_cache
from app.main import app
from app.models import User, Workspace
from app.replenishment_service import generate_all_recommendations
from app.seed import seed_database


class ApiEndpointsTest(unittest.TestCase):
    """Exercises every route through the real FastAPI app + routing layer.

    Unlike the other test files (which construct models/services directly),
    this hits each endpoint function as written in main.py — including
    every `record.some_relationship.field` access. That's specifically
    what the other test files can't catch: they don't go through the
    endpoint's serialization code at all. This test class is what caught
    `DemandRecord.warehouse` being un-set as a relationship (only
    `warehouse_id` existed), which only blew up inside GET /demand's
    response-building loop.
    """

    @classmethod
    def setUpClass(cls):
        clear_cache()

        # A single shared in-memory SQLite DB for the whole test class.
        # StaticPool is required here: without it, every new connection
        # (i.e. every request, since get_db() opens one per call) would
        # get its own blank in-memory database instead of sharing this one.
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=cls.engine)
        cls.TestSession = sessionmaker(bind=cls.engine)

        def override_get_db():
            db = cls.TestSession()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db

        # Seed directly through our own session — deliberately NOT using
        # TestClient's `with` lifespan context, so the app's @on_event
        # ("startup") hook (which uses the *real* database.py engine/
        # SessionLocal, pointed at nusaflow.db) never runs here.
        db = cls.TestSession()
        try:
            workspace = Workspace(name="Test Workspace", slug="test-workspace", is_demo=False)
            db.add(workspace)
            db.flush()
            user = User(workspace_id=workspace.id, email="apitest@example.com", password_hash="unused-in-tests", display_name="API Test User")
            db.add(user)
            db.commit()
            cls.workspace_id = workspace.id
            token = create_access_token(user.id)

            seed_database(db, workspace.id)
            cls.alert_summary = generate_alerts(db, workspace.id)
            cls.forecast_summary = generate_all_forecasts(db, workspace.id)
            cls.replenishment_summary = generate_all_recommendations(db, workspace.id)
        finally:
            db.close()

        # Setting Authorization here means every request through cls.client
        # is already authenticated — no need to touch every individual
        # self.client.get(...)/post(...) call site below.
        cls.client = TestClient(app, headers={"Authorization": f"Bearer {token}"})

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        clear_cache()

    def test_health(self):
        r = self.client.get("/api/v1/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ok")

    def test_protected_endpoint_without_token_is_401(self):
        # A client with no Authorization header at all — cls.client always
        # has one set (see setUpClass), so build a bare one here.
        anonymous_client = TestClient(app)
        r = anonymous_client.get("/api/v1/overview")
        self.assertEqual(r.status_code, 401)

    def test_workspace_isolation_across_two_accounts(self):
        """The one test in this file that matters most: a second
        workspace's token must not be able to read or mutate the first
        workspace's data, even when given that data's real object id.
        """
        db = self.TestSession()
        try:
            other_workspace = Workspace(name="Other Workspace", slug="other-workspace", is_demo=False)
            db.add(other_workspace)
            db.flush()
            other_user = User(workspace_id=other_workspace.id, email="other@example.com", password_hash="unused", display_name="Other User")
            db.add(other_user)
            db.commit()
            other_token = create_access_token(other_user.id)
        finally:
            db.close()

        other_client = TestClient(app, headers={"Authorization": f"Bearer {other_token}"})

        # The other workspace has zero shipments — GET /shipments should
        # reflect that, not leak the first workspace's 80 seeded ones.
        other_shipments = other_client.get("/api/v1/shipments").json()
        self.assertEqual(other_shipments, [])

        # A real shipment id from the FIRST workspace, accessed with the
        # SECOND workspace's token, must 404 — not return the real data.
        real_shipment_id = self.client.get("/api/v1/shipments").json()[0]["id"]
        cross_workspace_get = other_client.get(f"/api/v1/shipments/{real_shipment_id}")
        self.assertEqual(cross_workspace_get.status_code, 404)

        # ...and must not be mutable either.
        cross_workspace_mutate = other_client.post(f"/api/v1/shipments/{real_shipment_id}/simulate/advance")
        self.assertEqual(cross_workspace_mutate.status_code, 404)

    def test_overview(self):
        r = self.client.get("/api/v1/overview")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        for key in ("inventory_health", "active_shipments", "stockout_risk", "delayed_shipments"):
            self.assertIn(key, body)

    def test_inventory(self):
        r = self.client.get("/api/v1/inventory")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()), 60)  # 20 SKUs x 3 warehouses

    def test_inventory_analysis(self):
        r = self.client.get("/api/v1/inventory/analysis?page=1&page_size=5")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(len(body["items"]), 5)
        self.assertIn("stockout_risk", body["items"][0])

    def test_shipments_list_and_detail(self):
        r = self.client.get("/api/v1/shipments")
        self.assertEqual(r.status_code, 200)
        shipments = r.json()
        self.assertEqual(len(shipments), 80)

        shipment_id = shipments[0]["id"]
        detail = self.client.get(f"/api/v1/shipments/{shipment_id}")
        self.assertEqual(detail.status_code, 200)

        missing = self.client.get("/api/v1/shipments/999999")
        self.assertEqual(missing.status_code, 404)

    def test_shipment_events_and_simulate_advance(self):
        pending = next(s for s in self.client.get("/api/v1/shipments").json() if s["status"] == "pending")
        events_before = self.client.get(f"/api/v1/shipments/{pending['id']}/events").json()
        self.assertEqual(len(events_before), 1)  # just "Shipment Created" from seed

        advance = self.client.post(f"/api/v1/shipments/{pending['id']}/simulate/advance")
        self.assertEqual(advance.status_code, 200)
        self.assertEqual(advance.json()["shipment"]["status"], "in_transit")

        events_after = self.client.get(f"/api/v1/shipments/{pending['id']}/events").json()
        self.assertEqual(len(events_after), 2)

    def test_suppliers(self):
        r = self.client.get("/api/v1/suppliers")
        self.assertEqual(r.status_code, 200)
        # >=4, not ==4: other tests in this class (e.g. test_create_supplier)
        # share this same seeded workspace and may add more before this runs.
        self.assertGreaterEqual(len(r.json()), 4)

    def test_demand(self):
        # This is the endpoint that previously 500'd on every call because
        # DemandRecord.warehouse wasn't a real relationship.
        r = self.client.get("/api/v1/demand")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(len(body), 20)
        self.assertIn("warehouse", body[0])
        self.assertIn("product", body[0])

    def test_alerts_list_and_generate_and_patch(self):
        r = self.client.get("/api/v1/alerts")
        self.assertEqual(r.status_code, 200)
        alerts = r.json()
        self.assertGreater(len(alerts), 0)

        regen = self.client.post("/api/v1/alerts/generate")
        self.assertEqual(regen.status_code, 200)
        self.assertEqual(regen.json()["created"], 0)  # nothing changed since setUpClass seeded

        alert_id = alerts[0]["id"]
        patched = self.client.patch(f"/api/v1/alerts/{alert_id}?status=ACKNOWLEDGED")
        self.assertEqual(patched.status_code, 200)
        self.assertEqual(patched.json()["status"], "ACKNOWLEDGED")

        bad = self.client.patch(f"/api/v1/alerts/{alert_id}?status=NOT_A_STATUS")
        self.assertEqual(bad.status_code, 422)

    def test_root(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)

    def test_forecasts_summary_and_detail(self):
        summary = self.client.get("/api/v1/forecasts")
        self.assertEqual(summary.status_code, 200)
        forecasts = summary.json()
        self.assertEqual(len(forecasts), 60)  # one per (product, warehouse) pair

        sample = forecasts[0]
        detail = self.client.get(f"/api/v1/forecasts?sku={sample['product']}&warehouse={sample['warehouse']}&horizon_days=7")
        self.assertEqual(detail.status_code, 200)
        body = detail.json()
        self.assertEqual(len(body["forecast"]), 7)
        self.assertIn("methodology", body)
        self.assertIn("historical_demand", body)
        for point in body["forecast"]:
            self.assertIn("estimated_demand", point)
            self.assertLessEqual(point["lower_bound"], point["upper_bound"])

    def test_forecasts_unknown_pair_404(self):
        r = self.client.get("/api/v1/forecasts?sku=NOPE&warehouse=NOPE")
        self.assertEqual(r.status_code, 404)

    def test_forecasts_generate_single_pair(self):
        sample = self.client.get("/api/v1/forecasts").json()[0]
        r = self.client.post(f"/api/v1/forecasts/generate?sku={sample['product']}&warehouse={sample['warehouse']}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["product"], sample["product"])

        # Regenerating shouldn't create a duplicate row for the pair.
        after = self.client.get("/api/v1/forecasts").json()
        matches = [f for f in after if f["product"] == sample["product"] and f["warehouse"] == sample["warehouse"]]
        self.assertEqual(len(matches), 1)

    def test_replenishment_list_and_filter(self):
        r = self.client.get("/api/v1/replenishment")
        self.assertEqual(r.status_code, 200)
        recs = r.json()
        self.assertEqual(len(recs), 60)
        for field in ("forecast_demand", "safety_stock", "current_stock", "incoming_stock", "recommended_quantity", "explanation"):
            self.assertIn(field, recs[0])

        needs_reorder = self.client.get("/api/v1/replenishment?needs_reorder=true").json()
        self.assertTrue(all(r["recommended_quantity"] > 0 for r in needs_reorder))
        self.assertLessEqual(len(needs_reorder), len(recs))

    def test_replenishment_filter_by_pair_and_generate(self):
        sample = self.client.get("/api/v1/replenishment").json()[0]
        filtered = self.client.get(f"/api/v1/replenishment?sku={sample['product']}&warehouse={sample['warehouse']}")
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(len(filtered.json()), 1)

        regen = self.client.post(f"/api/v1/replenishment/generate?sku={sample['product']}&warehouse={sample['warehouse']}")
        self.assertEqual(regen.status_code, 200)

        after = self.client.get(f"/api/v1/replenishment?sku={sample['product']}&warehouse={sample['warehouse']}").json()
        self.assertEqual(len(after), 1)  # still just one row, not duplicated

    def test_replenishment_unknown_pair_404(self):
        r = self.client.post("/api/v1/replenishment/generate?sku=NOPE&warehouse=NOPE")
        self.assertEqual(r.status_code, 404)

    def test_simulation_run_preview_not_persisted(self):
        # Other tests in this class share the same DB (see setUpClass), so
        # assert against the count *before* this call rather than assuming
        # the list starts empty — that would make this test order-dependent.
        before = len(self.client.get("/api/v1/simulations").json())

        r = self.client.post("/api/v1/simulations/run", json={"demand_change_pct": 20, "shipment_delay_delta_days": 2})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        for key in ("baseline", "simulated", "delta"):
            self.assertIn(key, body)

        after = len(self.client.get("/api/v1/simulations").json())
        self.assertEqual(after, before)  # /run must not have created a scenario

    def test_simulation_create_list_detail_rerun(self):
        before = len(self.client.get("/api/v1/simulations").json())

        created = self.client.post(
            "/api/v1/simulations",
            json={"name": "Peak season", "demand_change_pct": 20, "lead_time_delta_days": 3, "shipment_delay_delta_days": 2},
        )
        self.assertEqual(created.status_code, 200)
        scenario_id = created.json()["id"]
        self.assertEqual(created.json()["name"], "Peak season")
        self.assertIsNotNone(created.json()["baseline"])
        self.assertIsNotNone(created.json()["simulated"])

        listed = self.client.get("/api/v1/simulations").json()
        self.assertEqual(len(listed), before + 1)

        detail = self.client.get(f"/api/v1/simulations/{scenario_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["id"], scenario_id)

        rerun = self.client.post(f"/api/v1/simulations/{scenario_id}/run")
        self.assertEqual(rerun.status_code, 200)

        missing = self.client.get("/api/v1/simulations/999999")
        self.assertEqual(missing.status_code, 404)

    def test_simulation_validates_param_bounds(self):
        r = self.client.post("/api/v1/simulations/run", json={"demand_change_pct": 999999})
        self.assertEqual(r.status_code, 422)

    # --- Master data CRUD (create/delete for empty-workspace usability) ---

    def test_create_warehouse_and_reject_duplicate_code(self):
        created = self.client.post("/api/v1/warehouses", json={"code": "WH-NEW", "name": "New DC", "city": "Bogor", "region": "Java"})
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["code"], "WH-NEW")

        dup = self.client.post("/api/v1/warehouses", json={"code": "WH-NEW", "name": "Dup", "city": "X", "region": "Y"})
        self.assertEqual(dup.status_code, 409)

    def test_create_product_and_reject_duplicate_sku(self):
        created = self.client.post("/api/v1/products", json={"sku": "SKU-NEW", "name": "New Widget", "category": "General", "unit_cost": 9.99, "lead_time_days": 4})
        self.assertEqual(created.status_code, 200)

        dup = self.client.post("/api/v1/products", json={"sku": "SKU-NEW", "name": "Dup", "category": "General", "unit_cost": 1.0, "lead_time_days": 1})
        self.assertEqual(dup.status_code, 409)

    def test_create_supplier(self):
        r = self.client.post("/api/v1/suppliers", json={"name": "Fresh Supplier", "lead_time_days": 3, "reliability_score": 0.95})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["name"], "Fresh Supplier")

    def test_full_master_data_lifecycle_and_delete_guards(self):
        warehouse = self.client.post("/api/v1/warehouses", json={"code": "WH-LIFE", "name": "Lifecycle DC", "city": "X", "region": "Y"}).json()
        product = self.client.post("/api/v1/products", json={"sku": "SKU-LIFE", "name": "Lifecycle Widget", "category": "General", "unit_cost": 5.0, "lead_time_days": 5}).json()

        inv = self.client.post(
            "/api/v1/inventory",
            json={"product_id": product["id"], "warehouse_id": warehouse["id"], "on_hand": 50, "safety_stock": 10, "reorder_point": 15, "incoming_qty": 0},
        )
        self.assertEqual(inv.status_code, 200)
        inv_id = inv.json()["id"]

        # Duplicate stock record for the same pair is rejected.
        dup_inv = self.client.post(
            "/api/v1/inventory",
            json={"product_id": product["id"], "warehouse_id": warehouse["id"], "on_hand": 1, "safety_stock": 1, "reorder_point": 1, "incoming_qty": 0},
        )
        self.assertEqual(dup_inv.status_code, 409)

        # Can't delete the warehouse or product while inventory references them.
        self.assertEqual(self.client.delete(f"/api/v1/warehouses/{warehouse['id']}").status_code, 409)
        self.assertEqual(self.client.delete(f"/api/v1/products/{product['id']}").status_code, 409)

        # Remove the inventory record, then both deletes succeed.
        self.assertEqual(self.client.delete(f"/api/v1/inventory/{inv_id}").status_code, 200)
        self.assertEqual(self.client.delete(f"/api/v1/warehouses/{warehouse['id']}").status_code, 200)
        self.assertEqual(self.client.delete(f"/api/v1/products/{product['id']}").status_code, 200)

    def test_delete_supplier_blocked_by_shipment(self):
        # The seeded demo data's suppliers all have shipments — pick one.
        supplier_id = self.client.get("/api/v1/suppliers").json()[0]["id"]
        r = self.client.delete(f"/api/v1/suppliers/{supplier_id}")
        self.assertEqual(r.status_code, 409)

    def test_inventory_create_rejects_cross_workspace_product(self):
        # A product id that's real, but belongs to a DIFFERENT workspace's token.
        other_signup = self.client.post(
            "/api/v1/auth/signup",
            json={"workspace_name": "Other CRUD Co", "display_name": "O", "email": "othercrud@example.com", "password": "hunter22222"},
        ).json()
        other_headers = {"Authorization": f"Bearer {other_signup['access_token']}"}
        other_product = self.client.post(
            "/api/v1/products",
            json={"sku": "SKU-OTHER", "name": "Other Widget", "category": "General", "unit_cost": 1.0, "lead_time_days": 1},
            headers=other_headers,
        ).json()

        warehouse = self.client.post("/api/v1/warehouses", json={"code": "WH-XCHK", "name": "X", "city": "X", "region": "Y"}).json()
        r = self.client.post(
            "/api/v1/inventory",
            json={"product_id": other_product["id"], "warehouse_id": warehouse["id"], "on_hand": 1, "safety_stock": 1, "reorder_point": 1, "incoming_qty": 0},
        )
        self.assertEqual(r.status_code, 404)

    def test_create_shipment_rejects_cross_workspace_ids(self):
        # Same isolation rule as above, for the new shipment endpoint: a
        # supplier id that is real, but belongs to a different workspace.
        other_signup = self.client.post(
            "/api/v1/auth/signup",
            json={"workspace_name": "Other Ship Co", "display_name": "O", "email": "othership@example.com", "password": "hunter22222"},
        ).json()
        other_headers = {"Authorization": f"Bearer {other_signup['access_token']}"}
        other_supplier = self.client.post(
            "/api/v1/suppliers",
            json={"name": "Other Supplier", "lead_time_days": 3, "reliability_score": 0.9},
            headers=other_headers,
        ).json()

        warehouse = self.client.post("/api/v1/warehouses", json={"code": "WH-SHIPX", "name": "X", "city": "X", "region": "Y"}).json()
        product = self.client.post("/api/v1/products", json={"sku": "SKU-SHIPX", "name": "X", "category": "General", "unit_cost": 1.0, "lead_time_days": 1}).json()

        r = self.client.post(
            "/api/v1/shipments",
            json={"product_id": product["id"], "warehouse_id": warehouse["id"], "supplier_id": other_supplier["id"], "quantity": 5, "transit_days": 4},
        )
        self.assertEqual(r.status_code, 404)


class EmptyWorkspaceOnboardingTest(unittest.TestCase):
    """The CLAUDE.md §4 user story, end to end through HTTP.

    A workspace created through signup starts empty. Before §5.1/§5.2 that
    meant it could never forecast, replenish, or track a shipment — those
    features only had data to work with in the seeded demo workspace. This
    class follows a fresh workspace from signup to a generated forecast and
    a simulated shipment, so the gap stays closed at the endpoint level.

    Deliberately its own class with its own database: the ApiEndpointsTest
    workspace is seeded and several of its tests assert exact row counts
    (80 shipments, 60 forecasts), which onboarding data would perturb.
    Each test also gets its OWN workspace, created through signup — that
    keeps every assertion absolute ("the list is empty", "90 days") and
    therefore independent of test order within the class.
    """

    @classmethod
    def setUpClass(cls):
        clear_cache()
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=cls.engine)
        cls.TestSession = sessionmaker(bind=cls.engine)

        def override_get_db():
            db = cls.TestSession()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        clear_cache()

    # Counter only used to keep each test's signup email unique — tests
    # can't share a workspace, so they can't share a login either.
    _signup_seq = 0

    def _fresh_client(self) -> TestClient:
        """A client for a brand-new empty workspace, via the real signup."""
        type(self)._signup_seq += 1
        signup = TestClient(app).post(
            "/api/v1/auth/signup",
            json={
                "workspace_name": f"Onboarding Co {type(self)._signup_seq}",
                "display_name": "New User",
                "email": f"onboarding{type(self)._signup_seq}@example.com",
                "password": "hunter22222",
            },
        )
        self.assertEqual(signup.status_code, 200, signup.text)
        return TestClient(app, headers={"Authorization": f"Bearer {signup.json()['access_token']}"})

    def _make_pair(self, client: TestClient, code: str, sku: str, supplier_name: str, with_stock: bool = True) -> dict:
        """Warehouse + product + supplier for a pair, optionally with stock."""
        warehouse = client.post("/api/v1/warehouses", json={"code": code, "name": f"{code} DC", "city": "Bandung", "region": "Java"}).json()
        product = client.post("/api/v1/products", json={"sku": sku, "name": f"{sku} Widget", "category": "General", "unit_cost": 3.0, "lead_time_days": 4}).json()
        supplier = client.post("/api/v1/suppliers", json={"name": supplier_name, "lead_time_days": 4, "reliability_score": 0.92}).json()
        if with_stock:
            inventory = client.post(
                "/api/v1/inventory",
                json={"product_id": product["id"], "warehouse_id": warehouse["id"], "on_hand": 60, "safety_stock": 12, "reorder_point": 20, "incoming_qty": 0},
            )
            self.assertEqual(inventory.status_code, 200, inventory.text)
        return {"warehouse": warehouse, "product": product, "supplier": supplier}

    def test_new_workspace_starts_empty(self):
        client = self._fresh_client()

        self.assertEqual(client.get("/api/v1/shipments").json(), [])
        self.assertEqual(client.get("/api/v1/forecasts").json(), [])
        self.assertEqual(client.get("/api/v1/replenishment").json(), [])
        self.assertEqual(client.get("/api/v1/demand").json(), [])

    def test_quick_estimate_opens_forecast_and_replenishment(self):
        client = self._fresh_client()
        self._make_pair(client, "WH-EST", "SKU-EST", "Estimate Supplier")

        estimate = client.post(
            "/api/v1/demand/quick-estimate",
            json={"sku": "SKU-EST", "warehouse": "WH-EST", "avg_units_per_day": 30},
        )
        self.assertEqual(estimate.status_code, 200, estimate.text)
        body = estimate.json()
        self.assertEqual(body["product"], "SKU-EST")
        self.assertEqual(body["warehouse"], "WH-EST")
        self.assertEqual(body["days_generated"], 90)
        self.assertEqual(body["days_skipped_existing"], 0)
        self.assertTrue(body["is_estimated"])

        # Before §5.1 these two calls were the dead end: "not enough demand
        # history yet". Now both succeed immediately after the estimate.
        forecast = client.post("/api/v1/forecasts/generate?sku=SKU-EST&warehouse=WH-EST")
        self.assertEqual(forecast.status_code, 200, forecast.text)
        self.assertTrue(forecast.json()["is_estimated"], "a forecast built on estimated history must be flagged as one")

        replenishment = client.post("/api/v1/replenishment/generate?sku=SKU-EST&warehouse=WH-EST")
        self.assertEqual(replenishment.status_code, 200, replenishment.text)
        self.assertTrue(replenishment.json()["is_estimated"])

        # The flags carry through to the reads the UI renders, so a yellow
        # badge can never be confused with seeded (real-demo) data.
        self.assertTrue(client.get("/api/v1/forecasts").json()[0]["is_estimated"])
        self.assertTrue(client.get("/api/v1/replenishment").json()[0]["is_estimated"])

        detail = client.get("/api/v1/forecasts?sku=SKU-EST&warehouse=WH-EST&horizon_days=7").json()
        self.assertTrue(detail["is_estimated"])
        self.assertIn("quick-estimate", detail["methodology"].lower())

        demand_rows = client.get("/api/v1/demand").json()
        self.assertTrue(demand_rows)
        self.assertTrue(all(row["is_estimated"] for row in demand_rows))

    def test_quick_estimate_rejects_unknown_pair_and_pair_without_stock(self):
        client = self._fresh_client()
        # Master data exists but no inventory record — the estimate must
        # refuse rather than manufacture history for a pair nobody stocks.
        self._make_pair(client, "WH-NOINV", "SKU-NOINV", "No Stock Supplier", with_stock=False)

        unknown = client.post("/api/v1/demand/quick-estimate", json={"sku": "NOPE", "warehouse": "WH-NOINV", "avg_units_per_day": 10})
        self.assertEqual(unknown.status_code, 404)

        no_stock = client.post("/api/v1/demand/quick-estimate", json={"sku": "SKU-NOINV", "warehouse": "WH-NOINV", "avg_units_per_day": 10})
        self.assertEqual(no_stock.status_code, 404)
        self.assertIn("inventory", no_stock.json()["detail"].lower())

        # Nothing was written while rejecting.
        self.assertEqual(client.get("/api/v1/demand").json(), [])

    def test_quick_estimate_second_call_leaves_existing_days_untouched(self):
        client = self._fresh_client()
        self._make_pair(client, "WH-EST2", "SKU-EST2", "Estimate Supplier 2")

        first = client.post("/api/v1/demand/quick-estimate", json={"sku": "SKU-EST2", "warehouse": "WH-EST2", "avg_units_per_day": 20})
        self.assertEqual(first.json()["days_generated"], 90)

        # Re-estimating the same pair must not overwrite or duplicate days.
        second = client.post("/api/v1/demand/quick-estimate", json={"sku": "SKU-EST2", "warehouse": "WH-EST2", "avg_units_per_day": 20})
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["days_generated"], 0)
        self.assertEqual(second.json()["days_skipped_existing"], 90)

        # Every day still belongs to exactly one record: the re-estimate
        # wrote nothing, and the 90 days from the first call are intact.
        self.assertEqual(second.json()["days_generated"], 0)
        rows = client.get("/api/v1/demand").json()
        # The read endpoint caps at 20 rows (it's a preview, not an export),
        # so this proves uniqueness of the surviving days, not their count.
        dates = [row["date"] for row in rows]
        self.assertEqual(len(dates), len(set(dates)))
        self.assertEqual(len(dates), 20)

    def test_create_shipment_then_simulate_advance(self):
        client = self._fresh_client()
        pair = self._make_pair(client, "WH-SHIP", "SKU-SHIP", "Ship Supplier")

        created = client.post(
            "/api/v1/shipments",
            json={
                "product_id": pair["product"]["id"],
                "warehouse_id": pair["warehouse"]["id"],
                "supplier_id": pair["supplier"]["id"],
                "quantity": 12,
                "transit_days": 5,
            },
        )
        self.assertEqual(created.status_code, 200, created.text)
        shipment = created.json()
        # Manual shipments get their own numbering range, starting from 1
        # in a fresh workspace, and begin pending (consistent with the
        # Created -> Departed step the simulate button takes next).
        self.assertEqual(shipment["shipment_number"], "SH-M0001")
        self.assertEqual(shipment["status"], "pending")
        self.assertEqual(shipment["eta_date"], (date.today() + timedelta(days=5)).isoformat())
        self.assertEqual(shipment["delay_days"], 0)

        events = client.get(f"/api/v1/shipments/{shipment['id']}/events").json()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_type"], "Shipment Created")

        # The manually created shipment is indistinguishable from a seeded
        # one once created — the existing advance flow works on it.
        advance = client.post(f"/api/v1/shipments/{shipment['id']}/simulate/advance")
        self.assertEqual(advance.status_code, 200, advance.text)
        self.assertEqual(advance.json()["shipment"]["status"], "in_transit")

        listed = client.get("/api/v1/shipments").json()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["id"], shipment["id"])

    def test_create_shipment_validates_eta_and_status_and_quantity(self):
        client = self._fresh_client()
        pair = self._make_pair(client, "WH-SHIPV", "SKU-SHIPV", "Ship Supplier V")
        base = {
            "product_id": pair["product"]["id"],
            "warehouse_id": pair["warehouse"]["id"],
            "supplier_id": pair["supplier"]["id"],
            "quantity": 3,
        }

        # Exactly one of eta_date / transit_days — not both, not neither.
        both = client.post("/api/v1/shipments", json={**base, "eta_date": "2026-12-01", "transit_days": 5})
        self.assertEqual(both.status_code, 422)

        neither = client.post("/api/v1/shipments", json=base)
        self.assertEqual(neither.status_code, 422)

        # A new shipment can't be born already delivered/cancelled.
        bad_status = client.post("/api/v1/shipments", json={**base, "transit_days": 5, "status": "delivered"})
        self.assertEqual(bad_status.status_code, 422)

        # eta_date can be given directly instead of a lead time.
        direct = client.post("/api/v1/shipments", json={**base, "eta_date": (date.today() + timedelta(days=10)).isoformat()})
        self.assertEqual(direct.status_code, 200)
        self.assertEqual(direct.json()["eta_date"], (date.today() + timedelta(days=10)).isoformat())

        # And unknown objects are rejected before anything is written: only
        # the one valid request above survives in the list.
        unknown_supplier = client.post("/api/v1/shipments", json={**base, "supplier_id": 999999, "transit_days": 5})
        self.assertEqual(unknown_supplier.status_code, 404)

        listed = client.get("/api/v1/shipments").json()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["eta_date"], (date.today() + timedelta(days=10)).isoformat())


if __name__ == "__main__":
    unittest.main()
