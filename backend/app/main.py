from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .alert_engine import generate_alerts
from .auth import get_current_workspace_id
from .auth_routes import router as auth_router
from .config import get_settings
from .database import SessionLocal, get_db
from .forecast_service import DEFAULT_HORIZON_DAYS, generate_all_forecasts, generate_forecast_for_pair
from .models import Alert, AlertStatus, DemandRecord, Forecast, Inventory, Product, ReplenishmentRecommendation, Shipment, ShipmentEvent, SimulationResult, SimulationScenario, Supplier, Warehouse
from .replenishment_service import generate_all_recommendations, generate_recommendation_for_pair
from .seed import ensure_demo_workspace, reset_workspace_data, seed_database
from .services import build_dashboard_summary
from .inventory_analysis import analyze_inventory, clear_cache
from .shipment_service import (
    ShipmentAlreadyTerminalError,
    advance_shipment,
    compute_delay_days,
    effective_status,
    get_events,
)
from .simulation_service import ScenarioParams, compute_comparison, create_and_run_scenario, rerun_scenario

settings = get_settings()

if settings.APP_ENV != "development" and settings.SECRET_KEY == "dev-only-insecure-secret-change-me":
    # Refuse to boot with the placeholder JWT signing key anywhere that
    # isn't local dev — starting "successfully" with this key would mean
    # every token is forgeable by anyone who reads this public repo.
    raise RuntimeError(
        "SECRET_KEY is still the development default. Set a real SECRET_KEY "
        "in the environment before starting the app outside APP_ENV=development."
    )

app = FastAPI(title="NusaFlow API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    # False, not True: this app authenticates via `Authorization: Bearer
    # <token>` set explicitly in JS (see frontend/lib/api.ts), never via
    # fetch's `credentials: 'include'` / automatic cross-origin cookies —
    # so there's nothing here that actually needs credentialed CORS mode.
    # This matters beyond just being unnecessary: browsers reject a
    # literal `Access-Control-Allow-Origin: *` when combined with
    # `Access-Control-Allow-Credentials: true`, so Starlette's
    # CORSMiddleware reflects the request's Origin header back instead —
    # meaning allow_credentials=True + CORS_ORIGINS="*" would silently
    # accept every origin, defeating the allowlist entirely. Setting this
    # False keeps a literal "*" meaning what it says.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)


@app.on_event("startup")
def startup_event():
    # Schema is managed by Alembic migrations now (run `alembic upgrade head`
    # before starting the app — see README). Seeding is still safe to run
    # here since seed_database() is idempotent (no-ops if data already exists).
    #
    # Only the demo workspace gets auto-seeded/auto-generated here. A
    # workspace created via POST /auth/signup starts empty on purpose (see
    # README) — its owner triggers alerts/forecasts/replenishment
    # generation themselves once they've added their own data, the same
    # way those endpoints already support on-demand regeneration.
    db = SessionLocal()
    try:
        demo_workspace = ensure_demo_workspace(db)
        seed_database(db, demo_workspace.id)
        generate_alerts(db, demo_workspace.id)  # so /alerts has data immediately, no manual trigger needed
        generate_all_forecasts(db, demo_workspace.id)  # so /forecasts has data immediately, no manual trigger needed
        generate_all_recommendations(db, demo_workspace.id)  # depends on forecasts existing — must run after the line above
    finally:
        db.close()


def _get_owned(db: Session, model, obj_id: int, workspace_id: int, label: str):
    """Load a row by id and verify it belongs to the caller's workspace.

    Returns 404 (not 403) either way — a wrong-workspace id should look
    identical to a nonexistent one, so URL-guessing can't be used to even
    confirm another workspace's row exists.
    """
    obj = db.get(model, obj_id)
    if obj is None or obj.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return obj


@app.get("/api/v1/health")
def health():
    return {"status": "ok", "service": "nusaflow-backend", "version": "1.0.0"}


@app.get("/api/v1/overview")
def overview(workspace_id: int = Depends(get_current_workspace_id), db: Session = Depends(get_db)):
    inventory_rows = [
        {
            "product": item.product.sku,
            "warehouse": item.warehouse.code,
            "on_hand": item.on_hand,
            "safety_stock": item.safety_stock,
            "reorder_point": item.reorder_point,
            "incoming_qty": item.incoming_qty,
        }
        for item in db.query(Inventory).filter(Inventory.workspace_id == workspace_id).all()
    ]
    shipments = [
        {
            "shipment_number": shipment.shipment_number,
            "status": effective_status(shipment),
            "delay_days": compute_delay_days(shipment),
            "eta_date": shipment.eta_date.isoformat() if shipment.eta_date else None,
            "quantity": shipment.quantity,
        }
        for shipment in db.query(Shipment).filter(Shipment.workspace_id == workspace_id).all()
    ]
    suppliers = [
        {"name": supplier.name, "reliability_score": supplier.reliability_score}
        for supplier in db.query(Supplier).filter(Supplier.workspace_id == workspace_id).all()
    ]
    return build_dashboard_summary(inventory_rows, shipments, suppliers)


@app.get("/api/v1/inventory")
def inventory(workspace_id: int = Depends(get_current_workspace_id), db: Session = Depends(get_db)):
    items = db.query(Inventory).filter(Inventory.workspace_id == workspace_id).all()
    return [
        {
            "id": item.id,
            "sku": item.product.sku,
            "product": item.product.name,
            "warehouse": item.warehouse.code,
            "on_hand": item.on_hand,
            "reserved": item.reserved,
            "safety_stock": item.safety_stock,
            "reorder_point": item.reorder_point,
            "incoming_qty": item.incoming_qty,
        }
        for item in items
    ]


def _serialize_shipment(shipment: Shipment) -> dict:
    return {
        "id": shipment.id,
        "shipment_number": shipment.shipment_number,
        "product": shipment.product.name,
        "warehouse": shipment.warehouse.code,
        "supplier": shipment.supplier.name,
        "quantity": shipment.quantity,
        # Live-computed, not the raw stored column: reflects "today" even if
        # nobody has advanced the simulation since the shipment was seeded.
        "status": effective_status(shipment),
        "eta_date": shipment.eta_date.isoformat(),
        "actual_delivery_date": shipment.actual_delivery_date.isoformat() if shipment.actual_delivery_date else None,
        "delay_days": compute_delay_days(shipment),
    }


@app.get("/api/v1/shipments")
def shipments(workspace_id: int = Depends(get_current_workspace_id), db: Session = Depends(get_db)):
    return [_serialize_shipment(shipment) for shipment in db.query(Shipment).filter(Shipment.workspace_id == workspace_id).all()]


@app.get("/api/v1/shipments/{shipment_id}")
def get_shipment(shipment_id: int, workspace_id: int = Depends(get_current_workspace_id), db: Session = Depends(get_db)):
    shipment = _get_owned(db, Shipment, shipment_id, workspace_id, "Shipment")
    return _serialize_shipment(shipment)


@app.get("/api/v1/shipments/{shipment_id}/events")
def shipment_events(shipment_id: int, workspace_id: int = Depends(get_current_workspace_id), db: Session = Depends(get_db)):
    """Full event timeline for one shipment (Phase 3 — real-time monitoring)."""
    _get_owned(db, Shipment, shipment_id, workspace_id, "Shipment")
    return [
        {
            "id": event.id,
            "event_type": event.event_type,
            "event_time": event.event_time.isoformat(),
            "details": event.details,
        }
        for event in get_events(db, shipment_id)
    ]


@app.post("/api/v1/shipments/{shipment_id}/simulate/advance")
def simulate_shipment_advance(shipment_id: int, workspace_id: int = Depends(get_current_workspace_id), db: Session = Depends(get_db)):
    """Advance a shipment one step through its lifecycle (Created -> Departed ->
    Checkpoint/Delay -> Delivered). Deterministic given current state + today's
    date; intended to be triggered from the UI (e.g. a "Simulate update" button)
    since this project intentionally has no always-on background scheduler.
    """
    shipment = _get_owned(db, Shipment, shipment_id, workspace_id, "Shipment")

    try:
        new_event = advance_shipment(db, shipment)
    except ShipmentAlreadyTerminalError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {
        "shipment": _serialize_shipment(shipment),
        "new_event": {
            "id": new_event.id,
            "event_type": new_event.event_type,
            "event_time": new_event.event_time.isoformat(),
            "details": new_event.details,
        },
    }


@app.get("/api/v1/suppliers")
def suppliers(workspace_id: int = Depends(get_current_workspace_id), db: Session = Depends(get_db)):
    results = db.query(Supplier).filter(Supplier.workspace_id == workspace_id).all()
    return [
        {
            "id": supplier.id,
            "name": supplier.name,
            "lead_time_days": supplier.lead_time_days,
            "delay_rate": supplier.delay_rate,
            "reliability_score": supplier.reliability_score,
        }
        for supplier in results
    ]


# Inventory analysis endpoints (Phase 2)
@app.get("/api/v1/inventory/analysis")
def inventory_analysis(
    window_days: int = 30,
    page: int = 1,
    page_size: int = 20,
    sku: str | None = None,
    warehouse: str | None = None,
    workspace_id: int = Depends(get_current_workspace_id),
    db: Session = Depends(get_db),
):
    """Return inventory analysis including avg daily demand, days of inventory, and stockout risk.

    Supports query params:
    - window_days (int)
    - page (int)
    - page_size (int)
    - sku (string)
    - warehouse (string)
    """
    return analyze_inventory(db, workspace_id, window_days=window_days, sku=sku, warehouse=warehouse, page=page, page_size=page_size)


@app.get("/api/v1/demand")
def demand(workspace_id: int = Depends(get_current_workspace_id), db: Session = Depends(get_db)):
    # LIMIT at the query level, not .all() followed by a Python-side slice —
    # with ~20 SKUs x 3 warehouses x 240 days (~170k rows), loading
    # everything just to keep the first 20 would be a real waste (AGENTS.md
    # §26: avoid loading entire datasets when pagination is appropriate).
    # DemandRecord has no workspace_id of its own (see models.py) — join
    # through Product, which does, to scope this.
    results = (
        db.query(DemandRecord)
        .join(Product, DemandRecord.product_id == Product.id)
        .filter(Product.workspace_id == workspace_id)
        .order_by(DemandRecord.record_date.asc())
        .limit(20)
        .all()
    )
    return [
        {
            "product": record.product.sku,
            "warehouse": record.warehouse.code,
            "date": record.record_date.isoformat(),
            "demand_qty": record.demand_qty,
        }
        for record in results
    ]


def _serialize_alert(alert: Alert) -> dict:
    return {
        "id": alert.id,
        "alert_type": alert.alert_type,
        "severity": alert.severity,
        "title": alert.title,
        "description": alert.description,
        "related_entity_type": alert.related_entity_type,
        "related_entity_id": alert.related_entity_id,
        "related_entity_label": alert.related_entity_label,
        "status": alert.status,
        "created_at": alert.created_at.isoformat() if alert.created_at else None,
        "updated_at": alert.updated_at.isoformat() if alert.updated_at else None,
        "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
    }


@app.get("/api/v1/alerts")
def list_alerts(
    status: str | None = None,
    severity: str | None = None,
    alert_type: str | None = None,
    workspace_id: int = Depends(get_current_workspace_id),
    db: Session = Depends(get_db),
):
    """List alerts (Phase 4). Defaults to everything; filter with ?status=OPEN etc.

    By default this does NOT re-run the rule engine — it just reads whatever
    is currently in the alerts table (kept fresh by the startup hook and by
    POST /alerts/generate). This keeps GET requests cheap and side-effect-free.
    """
    query = db.query(Alert).filter(Alert.workspace_id == workspace_id)
    if status:
        query = query.filter(Alert.status == status.upper())
    if severity:
        query = query.filter(Alert.severity == severity.upper())
    if alert_type:
        query = query.filter(Alert.alert_type == alert_type.upper())
    results = query.order_by(Alert.status.asc(), Alert.severity.desc(), Alert.created_at.desc()).all()
    return [_serialize_alert(a) for a in results]


@app.post("/api/v1/alerts/generate")
def run_alert_engine(workspace_id: int = Depends(get_current_workspace_id), db: Session = Depends(get_db)):
    """Manually re-run all 6 alert rules now (also runs automatically on
    startup). Returns a summary of what changed, not the full alert list —
    call GET /alerts afterwards to see the current state.
    """
    return generate_alerts(db, workspace_id)


@app.patch("/api/v1/alerts/{alert_id}")
def update_alert(alert_id: int, status: str, workspace_id: int = Depends(get_current_workspace_id), db: Session = Depends(get_db)):
    """Acknowledge or resolve an alert manually, e.g. ?status=ACKNOWLEDGED.

    Manually RESOLVED alerts stay resolved even if the engine runs again —
    the engine only ever resolves alerts whose underlying condition cleared,
    it never re-opens ones a human already closed.
    """
    alert = _get_owned(db, Alert, alert_id, workspace_id, "Alert")

    try:
        new_status = AlertStatus(status.upper())
    except ValueError:
        valid = ", ".join(s.value for s in AlertStatus)
        raise HTTPException(status_code=422, detail=f"status must be one of: {valid}")

    alert.status = new_status
    if new_status == AlertStatus.RESOLVED:
        alert.resolved_at = datetime.utcnow()
    db.commit()
    db.refresh(alert)
    return _serialize_alert(alert)


# --- Forecasts (Phase 5) ---


def _serialize_forecast_summary(forecast: Forecast) -> dict:
    """Compact form for the list endpoint — accuracy/method, no points."""
    return {
        "id": forecast.id,
        "product": forecast.product.sku,
        "warehouse": forecast.warehouse.code,
        "method": forecast.method,
        "horizon_days": forecast.horizon_days,
        "mae": round(forecast.mae, 2) if forecast.mae is not None else None,
        "mape": round(forecast.mape, 1) if forecast.mape is not None else None,
        "generated_at": forecast.generated_at.isoformat() if forecast.generated_at else None,
    }


def _serialize_forecast_detail(forecast: Forecast, history: list[dict], points: list) -> dict:
    """Full form for a single (sku, warehouse) — includes recent actuals
    (for the frontend to plot alongside the forecast) and the forecast
    points with an uncertainty band. Field is named `estimated_demand`,
    not `demand` or `predicted_demand`, on purpose — see AGENTS.md
    section 11: "Do not present forecasts as guaranteed predictions."
    """
    return {
        **_serialize_forecast_summary(forecast),
        "methodology": (
            "Baseline statistical forecast (moving average vs. weekday-seasonal "
            "average), backtested on the most recent 14 real days of history; "
            "whichever candidate had the lower error on that holdout was used. "
            "mae/mape describe that backtest's accuracy, not a guarantee about "
            "the future."
        ),
        "historical_demand": history,
        "forecast": [
            {
                "date": point.forecast_date.isoformat(),
                "day_offset": point.day_offset,
                "estimated_demand": point.estimated_demand,
                "lower_bound": point.lower_bound,
                "upper_bound": point.upper_bound,
            }
            for point in points
        ],
    }


@app.get("/api/v1/forecasts")
def list_forecasts(
    sku: str | None = None,
    warehouse: str | None = None,
    horizon_days: int | None = None,
    history_days: int = 30,
    workspace_id: int = Depends(get_current_workspace_id),
    db: Session = Depends(get_db),
):
    """Without sku+warehouse: summary list of every pair's latest forecast
    (method, accuracy) — an overview table. With both: the full forecast
    for that one pair, including recent actuals and forecast points, for
    charting. horizon_days optionally truncates the (already-generated,
    up to 30-day) point list to a shorter window (7 or 14).
    """
    if sku and warehouse:
        product = db.query(Product).filter(Product.sku == sku, Product.workspace_id == workspace_id).first()
        wh = db.query(Warehouse).filter(Warehouse.code == warehouse, Warehouse.workspace_id == workspace_id).first()
        if product is None or wh is None:
            raise HTTPException(status_code=404, detail="Unknown sku or warehouse")

        forecast = (
            db.query(Forecast)
            .filter(Forecast.product_id == product.id, Forecast.warehouse_id == wh.id, Forecast.workspace_id == workspace_id)
            .first()
        )
        if forecast is None:
            raise HTTPException(
                status_code=404,
                detail="No forecast for this pair yet (insufficient history, or it hasn't been generated). Try POST /forecasts/generate.",
            )

        history_start = date.today() - timedelta(days=history_days)
        history_rows = (
            db.query(DemandRecord)
            .filter(
                DemandRecord.product_id == product.id,
                DemandRecord.warehouse_id == wh.id,
                DemandRecord.record_date >= history_start,
            )
            .order_by(DemandRecord.record_date.asc())
            .all()
        )
        history = [{"date": r.record_date.isoformat(), "demand_qty": r.demand_qty} for r in history_rows]

        # Build the points list locally rather than reassigning
        # forecast.points — that's a live SQLAlchemy relationship with
        # cascade="all, delete-orphan", so setting it to a filtered list
        # would mark the excluded points for deletion on next flush. This
        # is a read-only GET; nothing here should ever write to the DB.
        points = list(forecast.points)
        if horizon_days:
            points = [p for p in points if p.day_offset <= horizon_days]

        return _serialize_forecast_detail(forecast, history, points)

    results = db.query(Forecast).filter(Forecast.workspace_id == workspace_id).order_by(Forecast.mae.desc()).all()
    return [_serialize_forecast_summary(f) for f in results]


@app.post("/api/v1/forecasts/generate")
def run_forecast_engine(
    sku: str | None = None,
    warehouse: str | None = None,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    workspace_id: int = Depends(get_current_workspace_id),
    db: Session = Depends(get_db),
):
    """Regenerate forecasts. With no params: every (product, warehouse)
    pair (also runs automatically on startup). With sku+warehouse: just
    that one pair.
    """
    if sku and warehouse:
        product = db.query(Product).filter(Product.sku == sku, Product.workspace_id == workspace_id).first()
        wh = db.query(Warehouse).filter(Warehouse.code == warehouse, Warehouse.workspace_id == workspace_id).first()
        if product is None or wh is None:
            raise HTTPException(status_code=404, detail="Unknown sku or warehouse")
        forecast = generate_forecast_for_pair(db, product, wh, horizon_days)
        if forecast is None:
            raise HTTPException(status_code=422, detail="Not enough demand history for this pair yet")
        return _serialize_forecast_summary(forecast)

    return generate_all_forecasts(db, workspace_id, horizon_days)


# --- Replenishment (Phase 6) ---


def _serialize_recommendation(rec: ReplenishmentRecommendation) -> dict:
    return {
        "id": rec.id,
        "product": rec.product.sku,
        "warehouse": rec.warehouse.code,
        "lead_time_days": rec.lead_time_days,
        "forecast_demand": rec.forecast_demand,
        "safety_stock": rec.safety_stock,
        "current_stock": rec.current_stock,
        "incoming_stock": rec.incoming_stock,
        "recommended_quantity": rec.recommended_quantity,
        "explanation": rec.explanation,
        "generated_at": rec.generated_at.isoformat() if rec.generated_at else None,
    }


@app.get("/api/v1/replenishment")
def list_replenishment(
    needs_reorder: bool = False,
    sku: str | None = None,
    warehouse: str | None = None,
    workspace_id: int = Depends(get_current_workspace_id),
    db: Session = Depends(get_db),
):
    """List current replenishment recommendations, highest-priority first.

    `?needs_reorder=true` filters to only recommended_quantity > 0 — the
    actionable subset. Without it, every (product, warehouse) pair is
    returned (including the ones that don't need anything right now),
    which is useful for confirming coverage rather than just seeing gaps.
    `?sku=&warehouse=` narrows to one specific pair.
    """
    query = db.query(ReplenishmentRecommendation).filter(ReplenishmentRecommendation.workspace_id == workspace_id)
    if sku:
        query = query.join(Product).filter(Product.sku == sku)
    if warehouse:
        query = query.join(Warehouse).filter(Warehouse.code == warehouse)
    if needs_reorder:
        query = query.filter(ReplenishmentRecommendation.recommended_quantity > 0)

    results = query.order_by(ReplenishmentRecommendation.recommended_quantity.desc()).all()
    return [_serialize_recommendation(r) for r in results]


@app.post("/api/v1/replenishment/generate")
def run_replenishment_engine(
    sku: str | None = None,
    warehouse: str | None = None,
    workspace_id: int = Depends(get_current_workspace_id),
    db: Session = Depends(get_db),
):
    """Regenerate recommendations. With no params: every pair (also runs
    automatically on startup, after forecasts). With sku+warehouse: just
    that one pair. Requires a forecast to already exist for the pair —
    run POST /forecasts/generate first if needed.
    """
    if sku and warehouse:
        product = db.query(Product).filter(Product.sku == sku, Product.workspace_id == workspace_id).first()
        wh = db.query(Warehouse).filter(Warehouse.code == warehouse, Warehouse.workspace_id == workspace_id).first()
        if product is None or wh is None:
            raise HTTPException(status_code=404, detail="Unknown sku or warehouse")
        inventory = (
            db.query(Inventory)
            .filter(Inventory.product_id == product.id, Inventory.warehouse_id == wh.id, Inventory.workspace_id == workspace_id)
            .first()
        )
        if inventory is None:
            raise HTTPException(status_code=404, detail="No inventory record for this pair")
        rec = generate_recommendation_for_pair(db, product, wh, inventory)
        if rec is None:
            raise HTTPException(status_code=422, detail="No forecast exists yet for this pair — run POST /forecasts/generate first")
        return _serialize_recommendation(rec)

    return generate_all_recommendations(db, workspace_id)


# --- What-If Simulation (Phase 7) ---


class SimulationParamsRequest(BaseModel):
    demand_change_pct: float = Field(0.0, ge=-100, le=500, description="e.g. 20 for +20% demand")
    lead_time_delta_days: int = Field(0, ge=-30, le=90, description="added to each product's lead time")
    shipment_delay_delta_days: int = Field(0, ge=-30, le=90, description="added to each active shipment's current delay")
    safety_stock_change_pct: float = Field(0.0, ge=-100, le=500, description="e.g. 10 for +10% safety stock")


class SimulationCreateRequest(SimulationParamsRequest):
    name: str = Field(..., min_length=1, max_length=120)


def _params_from_request(payload: SimulationParamsRequest) -> ScenarioParams:
    return ScenarioParams(
        demand_change_pct=payload.demand_change_pct,
        lead_time_delta_days=payload.lead_time_delta_days,
        shipment_delay_delta_days=payload.shipment_delay_delta_days,
        safety_stock_change_pct=payload.safety_stock_change_pct,
    )


def _serialize_metrics(result: SimulationResult | None) -> dict | None:
    if result is None:
        return None
    return {
        "stockout_risk_count": result.stockout_risk_count,
        "late_shipments_count": result.late_shipments_count,
        "service_level_pct": result.service_level_pct,
        "inventory_cost": result.inventory_cost,
        "replenishment_requirement": result.replenishment_requirement,
    }


def _serialize_scenario(db: Session, scenario: SimulationScenario) -> dict:
    baseline = (
        db.query(SimulationResult)
        .filter(SimulationResult.scenario_id == scenario.id, SimulationResult.is_baseline.is_(True))
        .order_by(SimulationResult.created_at.desc())
        .first()
    )
    simulated = (
        db.query(SimulationResult)
        .filter(SimulationResult.scenario_id == scenario.id, SimulationResult.is_baseline.is_(False))
        .order_by(SimulationResult.created_at.desc())
        .first()
    )
    return {
        "id": scenario.id,
        "name": scenario.name,
        "demand_change_pct": scenario.demand_change_pct,
        "lead_time_delta_days": scenario.lead_time_delta_days,
        "shipment_delay_delta_days": scenario.shipment_delay_delta_days,
        "safety_stock_change_pct": scenario.safety_stock_change_pct,
        "created_at": scenario.created_at.isoformat() if scenario.created_at else None,
        "baseline": _serialize_metrics(baseline),
        "simulated": _serialize_metrics(simulated),
    }


@app.post("/api/v1/simulations/run")
def run_simulation_preview(payload: SimulationParamsRequest, workspace_id: int = Depends(get_current_workspace_id), db: Session = Depends(get_db)):
    """Compute baseline vs. simulated for the given params WITHOUT saving
    anything — intended for a live preview as the user adjusts sliders.
    Use POST /simulations instead once they want to keep a scenario.
    """
    return compute_comparison(db, workspace_id, _params_from_request(payload))


@app.post("/api/v1/simulations")
def create_simulation(payload: SimulationCreateRequest, workspace_id: int = Depends(get_current_workspace_id), db: Session = Depends(get_db)):
    """Save a named scenario and compute+store its baseline/simulated result pair."""
    scenario = create_and_run_scenario(db, workspace_id, payload.name, _params_from_request(payload))
    return _serialize_scenario(db, scenario)


@app.get("/api/v1/simulations")
def list_simulations(workspace_id: int = Depends(get_current_workspace_id), db: Session = Depends(get_db)):
    scenarios = (
        db.query(SimulationScenario)
        .filter(SimulationScenario.workspace_id == workspace_id)
        .order_by(SimulationScenario.created_at.desc())
        .all()
    )
    return [_serialize_scenario(db, s) for s in scenarios]


@app.get("/api/v1/simulations/{scenario_id}")
def get_simulation(scenario_id: int, workspace_id: int = Depends(get_current_workspace_id), db: Session = Depends(get_db)):
    scenario = _get_owned(db, SimulationScenario, scenario_id, workspace_id, "Scenario")
    return _serialize_scenario(db, scenario)


@app.post("/api/v1/simulations/{scenario_id}/run")
def rerun_simulation(scenario_id: int, workspace_id: int = Depends(get_current_workspace_id), db: Session = Depends(get_db)):
    """Re-execute a saved scenario against CURRENT real data (a fresh
    result pair, since real data — shipments, forecasts — drifts over time).
    """
    scenario = _get_owned(db, SimulationScenario, scenario_id, workspace_id, "Scenario")
    rerun_scenario(db, scenario)
    return _serialize_scenario(db, scenario)


# Admin endpoints
@app.post("/api/v1/admin/cache/flush")
def flush_cache(request: Request, x_admin_token: str | None = Header(default=None)):
    """Flush the in-memory cache. Protected by ADMIN_API_KEY environment variable.

    Provide header `X-Admin-Token: <token>` or `Authorization: Bearer <token>`.
    """
    _require_admin_token(request, x_admin_token)
    clear_cache()
    return {"detail": "cache flushed"}


def _require_admin_token(request: Request, x_admin_token: str | None) -> None:
    admin_key = settings.ADMIN_API_KEY
    if not admin_key:
        raise HTTPException(status_code=503, detail="Admin API key not configured")

    token = x_admin_token
    if not token:
        auth = request.headers.get("authorization")
        if auth and auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1]

    normalized_token = token.strip().strip('"').strip("'") if token else None
    if not normalized_token or normalized_token != admin_key:
        raise HTTPException(status_code=401, detail="Invalid or missing admin token")


@app.post("/api/v1/admin/demo/reset")
def reset_demo_data(request: Request, x_admin_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    """Wipes and re-seeds the shared demo workspace. The demo is a single
    account every "Explore Demo" visitor logs into (see auth_routes.py),
    so it accumulates edits over time (simulated shipments, acknowledged
    alerts, saved scenarios) — this is the manual reset for that, protected
    the same way as /admin/cache/flush since there's no scheduler in this
    project to run it automatically (see README's known limitations).
    """
    _require_admin_token(request, x_admin_token)

    demo_workspace = ensure_demo_workspace(db)
    reset_workspace_data(db, demo_workspace.id)
    seed_database(db, demo_workspace.id)
    generate_alerts(db, demo_workspace.id)
    generate_all_forecasts(db, demo_workspace.id)
    generate_all_recommendations(db, demo_workspace.id)
    return {"detail": "demo workspace reset"}


@app.get("/")
def root():
    return {"message": "NusaFlow backend is running."}
