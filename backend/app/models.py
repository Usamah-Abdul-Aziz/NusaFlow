import enum
from datetime import datetime

from sqlalchemy import Boolean, Column, Date, DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint, false
from sqlalchemy.orm import relationship

from .database import Base


class Workspace(Base):
    """A tenant. Every other domain table (Product, Warehouse, Supplier,
    Inventory, Shipment, DemandRecord, Alert, Forecast,
    ReplenishmentRecommendation, SimulationScenario) carries a
    workspace_id and is filtered by it on every query — see
    app/auth.py's get_current_workspace_id() and app/main.py's endpoints.

    Child/detail tables one level down (ShipmentEvent, ForecastPoint,
    SimulationResult) do NOT carry their own workspace_id — they're only
    ever reached through an already workspace-checked parent (Shipment,
    Forecast, SimulationScenario respectively), so a second copy of the
    same fact would just be redundant data to keep in sync.
    """

    __tablename__ = "workspaces"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    slug = Column(String(60), unique=True, nullable=False, index=True)
    is_demo = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    users = relationship("User", back_populates="workspace", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(120), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    workspace = relationship("Workspace", back_populates="users")


class ShipmentStatus(str, enum.Enum):
    """Canonical shipment lifecycle states.

    Was previously a free String(40) column — meant any typo (e.g.
    "In_Transit" vs "in_transit") would silently break status filtering
    on the frontend without raising an error anywhere. A real Enum makes
    that a startup/insert-time error instead.
    """

    PENDING = "pending"
    IN_TRANSIT = "in_transit"
    DELAYED = "delayed"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    lead_time_days = Column(Integer, nullable=False, default=3)
    delay_rate = Column(Float, nullable=False, default=0.05)
    reliability_score = Column(Float, nullable=False, default=0.92)
    created_at = Column(DateTime, default=datetime.utcnow)

    shipments = relationship("Shipment", back_populates="supplier")


class Warehouse(Base):
    __tablename__ = "warehouses"
    __table_args__ = (UniqueConstraint("workspace_id", "code", name="uq_warehouse_workspace_code"),)

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    # code was globally unique before workspaces existed; now unique per
    # workspace only — two tenants can each have their own "WH-JKT".
    code = Column(String(20), nullable=False)
    name = Column(String(120), nullable=False)
    city = Column(String(80), nullable=False)
    region = Column(String(60), nullable=False)

    inventory = relationship("Inventory", back_populates="warehouse")
    shipments = relationship("Shipment", back_populates="warehouse")
    demand_records = relationship("DemandRecord", back_populates="warehouse")


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("workspace_id", "sku", name="uq_product_workspace_sku"),)

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    sku = Column(String(50), nullable=False)  # unique per workspace, not globally — see Warehouse.code
    name = Column(String(160), nullable=False)
    category = Column(String(80), nullable=False)
    unit_cost = Column(Float, nullable=False, default=10.0)
    lead_time_days = Column(Integer, nullable=False, default=5)

    inventory = relationship("Inventory", back_populates="product")
    demand_records = relationship("DemandRecord", back_populates="product")
    shipments = relationship("Shipment", back_populates="product")


class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    on_hand = Column(Integer, nullable=False, default=0)
    reserved = Column(Integer, nullable=False, default=0)
    safety_stock = Column(Integer, nullable=False, default=20)
    reorder_point = Column(Integer, nullable=False, default=25)
    incoming_qty = Column(Integer, nullable=False, default=0)

    product = relationship("Product", back_populates="inventory")
    warehouse = relationship("Warehouse", back_populates="inventory")


class Shipment(Base):
    __tablename__ = "shipments"
    __table_args__ = (UniqueConstraint("workspace_id", "shipment_number", name="uq_shipment_workspace_number"),)

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    shipment_number = Column(String(60), nullable=False)  # unique per workspace, not globally
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    quantity = Column(Integer, nullable=False, default=0)
    status = Column(
        Enum(
            ShipmentStatus,
            name="shipment_status",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
            create_constraint=True,  # also enforced as a CHECK on SQLite, not just Postgres' native enum
        ),
        nullable=False,
        default=ShipmentStatus.IN_TRANSIT,
    )
    eta_date = Column(Date, nullable=False)
    actual_delivery_date = Column(Date, nullable=True)
    delay_days = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    product = relationship("Product", back_populates="shipments")
    warehouse = relationship("Warehouse", back_populates="shipments")
    supplier = relationship("Supplier", back_populates="shipments")
    events = relationship("ShipmentEvent", back_populates="shipment")


class ShipmentEvent(Base):
    __tablename__ = "shipment_events"

    id = Column(Integer, primary_key=True, index=True)
    shipment_id = Column(Integer, ForeignKey("shipments.id"), nullable=False)
    event_type = Column(String(60), nullable=False)
    event_time = Column(DateTime, default=datetime.utcnow)
    details = Column(Text, nullable=True)

    shipment = relationship("Shipment", back_populates="events")


class AlertType(str, enum.Enum):
    LOW_STOCK = "LOW_STOCK"
    CRITICAL_STOCK = "CRITICAL_STOCK"
    STOCKOUT_RISK = "STOCKOUT_RISK"
    SHIPMENT_DELAY = "SHIPMENT_DELAY"
    SUPPLIER_DELAY = "SUPPLIER_DELAY"
    DEMAND_SPIKE = "DEMAND_SPIKE"


class AlertSeverity(str, enum.Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AlertStatus(str, enum.Enum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


class Alert(Base):
    """Rule-based alert raised by app/alert_engine.py (Phase 4).

    `dedupe_key` identifies "the same underlying condition" across engine
    runs (e.g. "STOCKOUT_RISK:inventory:42") so re-running the engine
    refreshes an existing OPEN alert instead of spamming duplicates, and
    so a condition that stops being true can be auto-resolved.
    """

    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    alert_type = Column(
        Enum(AlertType, name="alert_type", values_callable=lambda c: [m.value for m in c], create_constraint=True),
        nullable=False,
    )
    severity = Column(
        Enum(AlertSeverity, name="alert_severity", values_callable=lambda c: [m.value for m in c], create_constraint=True),
        nullable=False,
    )
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)

    # Polymorphic reference (product+warehouse pair, shipment, or supplier) —
    # deliberately not a hard FK since it can point at different tables.
    related_entity_type = Column(String(30), nullable=False)
    related_entity_id = Column(Integer, nullable=True)
    related_entity_label = Column(String(150), nullable=False)

    status = Column(
        Enum(AlertStatus, name="alert_status", values_callable=lambda c: [m.value for m in c], create_constraint=True),
        nullable=False,
        default=AlertStatus.OPEN,
    )
    dedupe_key = Column(String(160), nullable=False, index=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)


class DemandRecord(Base):
    """No workspace_id here on purpose, unlike other root tables — this is
    by far the highest-row-count table (~170k+ rows for the demo alone),
    and every query against it already goes through a product_id/
    warehouse_id pair sourced from an already workspace-checked Product/
    Warehouse/Inventory row (see forecast_service.py, alert_engine.py).
    Adding workspace_id here would be redundant data to keep in sync, not
    an extra safety net.
    """

    __tablename__ = "demand_records"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    record_date = Column(Date, nullable=False)
    demand_qty = Column(Integer, nullable=False, default=0)
    # True when this row came from POST /demand/quick-estimate (a user's
    # rough "about N units/day") rather than from the seed script or a
    # real sales feed. Forecasts and replenishment built on such rows are
    # still valid to compute, but the UI flags them as estimates.
    is_estimated = Column(Boolean, nullable=False, default=False, server_default=false())

    product = relationship("Product", back_populates="demand_records")
    warehouse = relationship("Warehouse", back_populates="demand_records")


class ForecastMethod(str, enum.Enum):
    MOVING_AVERAGE = "moving_average"
    WEEKDAY_SEASONAL = "weekday_seasonal"


class Forecast(Base):
    """One forecast run for a single (product, warehouse) pair — Phase 5.

    Regenerating a forecast for the same pair replaces this row (and its
    points) rather than accumulating history, same pattern as `Alert`:
    the current state is what matters, not a growing log. `mae`/`mape`
    come from backtesting on real held-out history (see
    app/forecast_service.py), not a hardcoded confidence number — that's
    what lets the API honestly say "estimated" instead of "guaranteed".
    """

    __tablename__ = "forecasts"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)

    method = Column(
        Enum(ForecastMethod, name="forecast_method", values_callable=lambda c: [m.value for m in c], create_constraint=True),
        nullable=False,
    )
    horizon_days = Column(Integer, nullable=False, default=30)

    # Backtest accuracy (14-day holdout) for the method that was actually
    # chosen — see forecast_service._backtest(). Not the accuracy of some
    # other method that was tried and rejected.
    mae = Column(Float, nullable=False)  # mean absolute error, in units/day
    mape = Column(Float, nullable=True)  # mean absolute % error; null if any actual was 0
    residual_std = Column(Float, nullable=False)  # backtest residual std dev, used for the uncertainty band

    generated_at = Column(DateTime, default=datetime.utcnow)

    product = relationship("Product")
    warehouse = relationship("Warehouse")
    points = relationship("ForecastPoint", back_populates="forecast", cascade="all, delete-orphan", order_by="ForecastPoint.forecast_date")


class ForecastPoint(Base):
    __tablename__ = "forecast_points"

    id = Column(Integer, primary_key=True, index=True)
    forecast_id = Column(Integer, ForeignKey("forecasts.id"), nullable=False)
    forecast_date = Column(Date, nullable=False)
    day_offset = Column(Integer, nullable=False)  # 1..horizon_days
    estimated_demand = Column(Float, nullable=False)
    lower_bound = Column(Float, nullable=False)
    upper_bound = Column(Float, nullable=False)

    forecast = relationship("Forecast", back_populates="points")


class ReplenishmentRecommendation(Base):
    """One recommendation for a single (product, warehouse) pair — Phase 6.

    Same "replace, don't accumulate" pattern as Forecast: regenerating for
    a pair replaces this row rather than growing a history table. Every
    input to the formula is stored alongside the result (not just the
    final number) specifically so `explanation` can show its work —
    AGENTS.md section 11: "Every recommendation must be explainable."
    """

    __tablename__ = "replenishment_recommendations"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)

    lead_time_days = Column(Integer, nullable=False)
    forecast_demand = Column(Float, nullable=False)
    safety_stock = Column(Integer, nullable=False)
    current_stock = Column(Integer, nullable=False)
    incoming_stock = Column(Integer, nullable=False)
    recommended_quantity = Column(Float, nullable=False)
    explanation = Column(Text, nullable=False)

    generated_at = Column(DateTime, default=datetime.utcnow)

    product = relationship("Product")
    warehouse = relationship("Warehouse")


class SimulationScenario(Base):
    """A saved what-if scenario — Phase 7. Created via POST /simulations
    (named, persisted). POST /simulations/run computes the same comparison
    WITHOUT creating one of these, for quick live-preview use where saving
    every slider tweak would just clutter the scenario list.
    """

    __tablename__ = "simulation_scenarios"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    name = Column(String(120), nullable=False)

    demand_change_pct = Column(Float, nullable=False, default=0.0)
    lead_time_delta_days = Column(Integer, nullable=False, default=0)
    shipment_delay_delta_days = Column(Integer, nullable=False, default=0)
    safety_stock_change_pct = Column(Float, nullable=False, default=0.0)

    created_at = Column(DateTime, default=datetime.utcnow)

    results = relationship("SimulationResult", back_populates="scenario", cascade="all, delete-orphan")


class SimulationResult(Base):
    """One side of a baseline-vs-simulated comparison (is_baseline
    distinguishes which). A scenario gets a fresh pair of these every time
    it's run — re-running an old scenario (see simulation_service.rerun_scenario)
    adds a new pair rather than overwriting, since "how does this
    hypothetical look today vs. when I first saved it" is itself useful
    signal as real operational data drifts.
    """

    __tablename__ = "simulation_results"

    id = Column(Integer, primary_key=True, index=True)
    scenario_id = Column(Integer, ForeignKey("simulation_scenarios.id"), nullable=False)
    is_baseline = Column(Boolean, nullable=False)

    stockout_risk_count = Column(Integer, nullable=False)
    late_shipments_count = Column(Integer, nullable=False)
    service_level_pct = Column(Float, nullable=False)
    inventory_cost = Column(Float, nullable=False)
    replenishment_requirement = Column(Float, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    scenario = relationship("SimulationScenario", back_populates="results")
