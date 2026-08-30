import random
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from .auth import hash_password
from .models import (
    Alert,
    DemandRecord,
    Forecast,
    ForecastPoint,
    Inventory,
    Product,
    ReplenishmentRecommendation,
    Shipment,
    ShipmentEvent,
    ShipmentStatus,
    SimulationResult,
    SimulationScenario,
    Supplier,
    User,
    Warehouse,
    Workspace,
)

# Fixed seed => the same synthetic dataset every time we (re)seed. Keeps
# demos and screenshots reproducible instead of reshuffling on every restart.
_RNG = random.Random(2026)

DEMAND_HISTORY_DAYS = 240  # ~8 months, within the 6-12 month target in AGENTS.md
SHIPMENT_COUNT = 80

# tier -> (daily demand range, default safety_stock, default reorder_point)
TIERS = {
    "high": {"demand": (8, 15), "safety_stock": 35, "reorder_point": 55},
    "medium": {"demand": (3, 7), "safety_stock": 20, "reorder_point": 32},
    "low": {"demand": (1, 3), "safety_stock": 10, "reorder_point": 16},
}

# (sku, name, category, unit_cost, lead_time_days, tier, seasonal_window)
# seasonal_window = (start_day_offset, end_day_offset, multiplier) measured
# from the start of the demand-history window, or None if not seasonal.
# The two seasonal SKUs below are deliberately positioned in the LAST ~10
# days of the window (not the middle) so the Phase 4 DEMAND_SPIKE check —
# which compares the most recent 7 days against the prior 21-day baseline —
# has something real to detect right out of a fresh seed, instead of a
# spike that already ended months ago.
PRODUCTS = [
    ("SKU-101", "Toner Cartridge", "Office", 68.0, 6, "medium", None),
    ("SKU-102", "Industrial Cable 50m", "Electrical", 42.0, 5, "medium", None),
    ("SKU-103", "Safety Gloves (pair)", "PPE", 18.0, 4, "high", None),
    ("SKU-104", "Packaging Tape Roll", "Packaging", 9.0, 3, "high", None),
    ("SKU-105", "Hydraulic Seal Kit", "Mechanical", 72.0, 7, "low", None),
    ("SKU-106", "A4 Paper Ream", "Office", 6.5, 3, "high", None),
    ("SKU-107", "LED Panel Light", "Electrical", 55.0, 8, "medium", None),
    ("SKU-108", "Safety Helmet", "PPE", 25.0, 5, "medium", None),
    ("SKU-109", "Bubble Wrap Roll", "Packaging", 14.0, 4, "medium", None),
    ("SKU-110", "Ball Bearing Set", "Mechanical", 33.0, 6, "medium", None),
    ("SKU-111", "Whiteboard Marker Pack", "Office", 4.0, 2, "high", (230, 239, 1.7)),
    ("SKU-112", "Circuit Breaker 32A", "Electrical", 61.0, 9, "low", None),
    ("SKU-113", "Safety Goggles", "PPE", 12.0, 3, "high", None),
    ("SKU-114", "Corrugated Box (Medium)", "Packaging", 3.5, 2, "high", (234, 239, 2.3)),
    ("SKU-115", "Steel Mounting Bracket", "Mechanical", 21.0, 5, "medium", None),
    ("SKU-116", "Extension Cord 10m", "Electrical", 19.5, 4, "medium", None),
    ("SKU-117", "Disposable Face Mask (box)", "PPE", 8.0, 3, "high", None),
    ("SKU-118", "Stretch Film Roll", "Packaging", 17.0, 4, "medium", None),
    ("SKU-119", "Industrial Degreaser 5L", "Cleaning", 27.0, 6, "low", None),
    ("SKU-120", "Floor Cleaning Pads", "Cleaning", 11.0, 3, "medium", None),
]

# Warehouses get a demand multiplier so the same SKU doesn't move at an
# identical pace everywhere (Jakarta DC is the busiest hub).
WAREHOUSE_DEMAND_MULTIPLIER = {"WH-JKT": 1.3, "WH-BDG": 1.0, "WH-SBY": 0.8}


def _weekday_factor(day: date) -> float:
    return 0.6 if day.weekday() >= 5 else 1.0


def _seasonal_factor(day_index: int, seasonal_window) -> float:
    if not seasonal_window:
        return 1.0
    start, end, multiplier = seasonal_window
    return multiplier if start <= day_index <= end else 1.0


def ensure_demo_workspace(db: Session) -> Workspace:
    """Idempotently creates the one well-known demo workspace + its shared
    Demo User, used by POST /auth/demo. Distinct from seed_database(),
    which fills a workspace with synthetic data — this just creates the
    workspace/user shell; the caller still has to call seed_database()
    with the returned id to populate it.
    """
    workspace = db.query(Workspace).filter(Workspace.is_demo.is_(True)).first()
    if workspace is not None:
        return workspace

    workspace = Workspace(name="Nusantara Distribution", slug="demo", is_demo=True)
    db.add(workspace)
    db.flush()

    db.add(
        User(
            workspace_id=workspace.id,
            email="demo@nusaflow.app",
            # Never checked by a login flow — POST /auth/demo issues a
            # token for this user unconditionally, no password required.
            # Hashed anyway so password_hash is never left null/fake.
            password_hash=hash_password("not-a-real-login-path"),
            display_name="Demo User",
        )
    )
    db.commit()
    db.refresh(workspace)
    return workspace


def reset_workspace_data(db: Session, workspace_id: int) -> None:
    """Deletes every domain row for a workspace, in FK-safe (children
    before parents) order, WITHOUT deleting the Workspace or User rows
    themselves. Used by the admin demo-reset endpoint so the shared demo
    workspace (see ensure_demo_workspace) can be restored to a clean
    state after visitors have been clicking "Simulate next step" /
    acknowledging alerts / saving scenarios on it for a while.
    """
    product_ids = [p.id for p in db.query(Product.id).filter(Product.workspace_id == workspace_id).all()]
    shipment_ids = [s.id for s in db.query(Shipment.id).filter(Shipment.workspace_id == workspace_id).all()]
    forecast_ids = [f.id for f in db.query(Forecast.id).filter(Forecast.workspace_id == workspace_id).all()]
    scenario_ids = [s.id for s in db.query(SimulationScenario.id).filter(SimulationScenario.workspace_id == workspace_id).all()]

    if shipment_ids:
        db.query(ShipmentEvent).filter(ShipmentEvent.shipment_id.in_(shipment_ids)).delete(synchronize_session=False)
    db.query(Shipment).filter(Shipment.workspace_id == workspace_id).delete(synchronize_session=False)

    if forecast_ids:
        db.query(ForecastPoint).filter(ForecastPoint.forecast_id.in_(forecast_ids)).delete(synchronize_session=False)
    db.query(Forecast).filter(Forecast.workspace_id == workspace_id).delete(synchronize_session=False)

    db.query(ReplenishmentRecommendation).filter(ReplenishmentRecommendation.workspace_id == workspace_id).delete(synchronize_session=False)
    db.query(Alert).filter(Alert.workspace_id == workspace_id).delete(synchronize_session=False)

    if scenario_ids:
        db.query(SimulationResult).filter(SimulationResult.scenario_id.in_(scenario_ids)).delete(synchronize_session=False)
    db.query(SimulationScenario).filter(SimulationScenario.workspace_id == workspace_id).delete(synchronize_session=False)

    if product_ids:
        db.query(DemandRecord).filter(DemandRecord.product_id.in_(product_ids)).delete(synchronize_session=False)
    db.query(Inventory).filter(Inventory.workspace_id == workspace_id).delete(synchronize_session=False)
    db.query(Product).filter(Product.workspace_id == workspace_id).delete(synchronize_session=False)
    db.query(Warehouse).filter(Warehouse.workspace_id == workspace_id).delete(synchronize_session=False)
    db.query(Supplier).filter(Supplier.workspace_id == workspace_id).delete(synchronize_session=False)
    db.commit()


def seed_database(db: Session, workspace_id: int):
    if db.query(Supplier).filter(Supplier.workspace_id == workspace_id).first() is not None:
        return

    suppliers = [
        Supplier(workspace_id=workspace_id, name="PT Sinar Logistik", lead_time_days=3, delay_rate=0.08, reliability_score=0.94),
        Supplier(workspace_id=workspace_id, name="Nusa Freight Indonesia", lead_time_days=5, delay_rate=0.12, reliability_score=0.89),
        Supplier(workspace_id=workspace_id, name="Bali Supply Co.", lead_time_days=4, delay_rate=0.07, reliability_score=0.91),
        Supplier(workspace_id=workspace_id, name="Kalimantan Goods", lead_time_days=6, delay_rate=0.38, reliability_score=0.71),
    ]
    db.add_all(suppliers)
    db.flush()

    warehouses = [
        Warehouse(workspace_id=workspace_id, code="WH-JKT", name="Jakarta DC", city="Jakarta", region="Java"),
        Warehouse(workspace_id=workspace_id, code="WH-BDG", name="Bandung Hub", city="Bandung", region="Java"),
        Warehouse(workspace_id=workspace_id, code="WH-SBY", name="Surabaya DC", city="Surabaya", region="East Java"),
    ]
    db.add_all(warehouses)
    db.flush()

    products = [
        Product(workspace_id=workspace_id, sku=sku, name=name, category=category, unit_cost=cost, lead_time_days=lead_time)
        for sku, name, category, cost, lead_time, tier, seasonal in PRODUCTS
    ]
    db.add_all(products)
    db.flush()
    product_meta = {row[0]: (row[5], row[6]) for row in PRODUCTS}  # sku -> (tier, seasonal_window)

    # --- Inventory: deliberately spread across understocked / healthy / ---
    # --- overstocked so the dashboard shows a realistic risk mix.       ---
    inventory_rows: list[Inventory] = []
    for product in products:
        tier, _ = product_meta[product.sku]
        tier_cfg = TIERS[tier]
        base_demand = sum(tier_cfg["demand"]) / 2
        for warehouse in warehouses:
            wh_demand = base_demand * WAREHOUSE_DEMAND_MULTIPLIER[warehouse.code]
            # Coverage target varies per (product, warehouse): some pairs
            # deliberately land below safety stock (stockout-risk demo),
            # most are healthy, a few are overstocked.
            coverage_days = _RNG.choice([3, 5, 8, 12, 18, 25, 35, 45])
            on_hand = max(0, round(wh_demand * coverage_days + _RNG.uniform(-5, 5)))
            inv = Inventory(
                workspace_id=workspace_id,
                product_id=product.id,
                warehouse_id=warehouse.id,
                on_hand=on_hand,
                reserved=_RNG.randint(0, max(1, tier_cfg["safety_stock"] // 4)),
                safety_stock=tier_cfg["safety_stock"],
                reorder_point=tier_cfg["reorder_point"],
                incoming_qty=0,  # filled in after shipments are generated below
            )
            inventory_rows.append(inv)
    db.add_all(inventory_rows)
    db.flush()
    inventory_by_key = {(inv.product_id, inv.warehouse_id): inv for inv in inventory_rows}

    # --- Demand history: 8 months, varying by SKU tier, warehouse, ---
    # --- weekday, and a seasonal bump for two flagged SKUs.        ---
    history_start = date.today() - timedelta(days=DEMAND_HISTORY_DAYS)
    demand_rows = []
    for product in products:
        tier, seasonal_window = product_meta[product.sku]
        low, high = TIERS[tier]["demand"]
        base = _RNG.uniform(low, high)
        for warehouse in warehouses:
            wh_multiplier = WAREHOUSE_DEMAND_MULTIPLIER[warehouse.code]
            for day_index in range(DEMAND_HISTORY_DAYS):
                current_day = history_start + timedelta(days=day_index)
                noise = _RNG.uniform(0.75, 1.25)
                qty = (
                    base
                    * wh_multiplier
                    * _weekday_factor(current_day)
                    * _seasonal_factor(day_index, seasonal_window)
                    * noise
                )
                demand_rows.append(
                    {
                        "product_id": product.id,
                        "warehouse_id": warehouse.id,
                        "record_date": current_day,
                        "demand_qty": max(0, round(qty)),
                    }
                )
    # Bulk insert: ~20 SKUs x 3 warehouses x 240 days is too many rows to
    # add one ORM object at a time without noticeably slowing down seeding.
    db.bulk_insert_mappings(DemandRecord, demand_rows)

    # --- Shipments: spread across past (delivered/cancelled), near-term ---
    # --- (in transit, some already naturally overdue) and future        ---
    # --- (pending). Outcome odds are driven by each supplier's own      ---
    # --- delay_rate, not a flat coin flip.                              ---
    today = date.today()
    incoming_by_key: dict[tuple[int, int], int] = {}

    past_count = round(SHIPMENT_COUNT * 0.56)  # ~45, already resolved
    near_term_count = round(SHIPMENT_COUNT * 0.25)  # ~20, active now
    future_count = SHIPMENT_COUNT - past_count - near_term_count  # ~15, not yet departed

    def created_offset_days_for_bucket(bucket: str) -> int:
        # How many days ago the order was PLACED. eta_date is then derived
        # forward from created_at (never the other way around) so a
        # shipment's "Created" event can never end up timestamped in the
        # future — that previously broke advance_shipment's "look at the
        # last event" logic, since events are ordered by event_time.
        if bucket == "past":
            return _RNG.randint(25, 110)
        if bucket == "near_term":
            return _RNG.randint(3, 14)
        return _RNG.randint(0, 4)  # future/pending: order just placed

    buckets = ["past"] * past_count + ["near_term"] * near_term_count + ["future"] * future_count
    _RNG.shuffle(buckets)

    for i, bucket in enumerate(buckets, start=1):
        product = _RNG.choice(products)
        warehouse = _RNG.choice(warehouses)
        supplier = _RNG.choice(suppliers)
        tier, _ = product_meta[product.sku]
        qty_range = {"high": (80, 200), "medium": (40, 120), "low": (15, 60)}[tier]
        quantity = _RNG.randint(*qty_range)

        transit_days = max(2, supplier.lead_time_days + _RNG.randint(-1, 2))
        created_at_date = today - timedelta(days=created_offset_days_for_bucket(bucket))
        created_at = datetime.combine(created_at_date, datetime.min.time()) + timedelta(hours=_RNG.randint(6, 18))
        eta_date = created_at_date + timedelta(days=transit_days)

        shipment = Shipment(
            workspace_id=workspace_id,
            shipment_number=f"SH-{1000 + i}",
            product_id=product.id,
            warehouse_id=warehouse.id,
            supplier_id=supplier.id,
            quantity=quantity,
            eta_date=eta_date,
            created_at=created_at,
        )
        shipment.events = [
            ShipmentEvent(event_type="Shipment Created", event_time=created_at, details="Order created in system")
        ]

        if bucket == "past":
            if _RNG.random() < 0.04:  # a handful of cancellations for realism
                shipment.status = ShipmentStatus.CANCELLED
                shipment.delay_days = 0
                shipment.events.append(
                    ShipmentEvent(
                        event_type="Shipment Cancelled",
                        event_time=created_at + timedelta(days=1),
                        details="Cancelled by supplier before dispatch",
                    )
                )
            else:
                is_late = _RNG.random() < supplier.delay_rate
                delivered_offset = _RNG.randint(1, 5) if is_late else _RNG.randint(-1, 0)
                actual_delivery = eta_date + timedelta(days=delivered_offset)
                shipment.status = ShipmentStatus.DELIVERED
                shipment.actual_delivery_date = actual_delivery
                shipment.delay_days = max(0, (actual_delivery - eta_date).days)

                departed_at = created_at + timedelta(hours=_RNG.randint(2, 10))
                shipment.events.append(
                    ShipmentEvent(event_type="Shipment Departed", event_time=departed_at, details="Outbound dispatch confirmed")
                )
                if is_late:
                    shipment.events.append(
                        ShipmentEvent(
                            event_type="Delay Detected",
                            event_time=datetime.combine(eta_date, datetime.min.time()),
                            details=f"Shipment running {shipment.delay_days} day(s) behind schedule",
                        )
                    )
                else:
                    shipment.events.append(
                        ShipmentEvent(
                            event_type="Checkpoint Reached",
                            event_time=departed_at + timedelta(days=max(1, transit_days // 2)),
                            details="Shipment passed an intermediate checkpoint",
                        )
                    )
                shipment.events.append(
                    ShipmentEvent(
                        event_type="Shipment Delivered",
                        event_time=datetime.combine(actual_delivery, datetime.min.time()),
                        details="Delivered on schedule" if not is_late else f"Delivered {shipment.delay_days} day(s) late",
                    )
                )

        elif bucket == "near_term":
            # In transit now. If eta_date has already slipped into the past,
            # effective_status()/compute_delay_days() (shipment_service.py)
            # will report it as DELAYED live — no need to hardcode that here.
            shipment.status = ShipmentStatus.IN_TRANSIT
            shipment.delay_days = 0
            departed_at = created_at + timedelta(hours=_RNG.randint(2, 10))
            shipment.events.append(
                ShipmentEvent(event_type="Shipment Departed", event_time=departed_at, details="Outbound dispatch confirmed")
            )
            key = (product.id, warehouse.id)
            incoming_by_key[key] = incoming_by_key.get(key, 0) + quantity

        else:  # future
            shipment.status = ShipmentStatus.PENDING
            shipment.delay_days = 0
            key = (product.id, warehouse.id)
            incoming_by_key[key] = incoming_by_key.get(key, 0) + quantity

        db.add(shipment)

    # Incoming inventory should reflect shipments that haven't arrived yet —
    # ties Inventory and Shipment together instead of leaving incoming_qty
    # as an arbitrary static number (AGENTS.md section 9: respect relationships).
    for key, qty in incoming_by_key.items():
        inv = inventory_by_key.get(key)
        if inv is not None:
            inv.incoming_qty = qty

    db.commit()
