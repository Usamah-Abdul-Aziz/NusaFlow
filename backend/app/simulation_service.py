"""
What-If Simulation — Phase 7.

Four scenario parameters (AGENTS.md section 11):
  - demand_change_pct:          e.g. +20 means demand is scaled by 1.20
  - lead_time_delta_days:       added to each product's lead_time_days
  - shipment_delay_delta_days:  added to each active shipment's current delay
  - safety_stock_change_pct:    e.g. +10 means safety stock is scaled by 1.10

Five metrics, all computed by ONE function (`_compute_metrics`) called twice
— once with all deltas at zero (the baseline/"current" scenario) and once
with the user's params (the "simulated" scenario). Using the same code path
for both is deliberate: it's the only way to guarantee the comparison is
apples-to-apples rather than two subtly different formulas drifting apart.

Every metric reuses an earlier phase's logic instead of re-deriving it:
  - stockout risk        -> same threshold shape as analyze_inventory_item()
                             (Phase 2), just fed adjusted demand/lead-time/
                             safety-stock instead of the real values.
  - replenishment req.    -> same formula as replenishment_service.py
                             (Phase 6), fed adjusted forecast demand and
                             safety stock.
  - inventory cost        -> unit_cost x the (adjusted) recommended
                             replenishment quantity — "what would it cost to
                             stay covered under this scenario", not the
                             value of stock already on the shelf (which
                             doesn't change with a hypothetical).
  - late shipments        -> same effective_status()/compute_delay_days()
                             shape as Phase 3, with shipment_delay_delta_days
                             added to the real delay.
  - service level         -> % of (product, warehouse) pairs NOT at
                             stockout risk under the scenario.

Nothing here writes to Inventory, Shipment, Forecast, or any other
operational table — AGENTS.md section 11: "The simulation should NOT
modify real operational data." The only writes are to the simulation's
own SimulationScenario/SimulationResult tables, and only when the caller
explicitly asks to persist (POST /simulations, not POST /simulations/run).
"""
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from .inventory_analysis import avg_daily_demand
from .models import Forecast, Inventory, Shipment, SimulationResult, SimulationScenario
from .shipment_service import DELIVERED, CANCELLED, compute_delay_days


@dataclass
class ScenarioParams:
    demand_change_pct: float = 0.0
    lead_time_delta_days: int = 0
    shipment_delay_delta_days: int = 0
    safety_stock_change_pct: float = 0.0


def _forecast_demand_over_days(forecast: Forecast | None, days: int, demand_multiplier: float) -> float:
    if forecast is None or days <= 0:
        return 0.0
    points = sorted(forecast.points, key=lambda p: p.day_offset)[:days]
    return sum(p.estimated_demand for p in points) * demand_multiplier


def _compute_metrics(db: Session, workspace_id: int, params: ScenarioParams) -> dict:
    demand_multiplier = 1 + params.demand_change_pct / 100
    safety_multiplier = 1 + params.safety_stock_change_pct / 100

    inventory_rows = db.query(Inventory).filter(Inventory.workspace_id == workspace_id).all()
    forecasts_by_pair = {
        (f.product_id, f.warehouse_id): f for f in db.query(Forecast).filter(Forecast.workspace_id == workspace_id).all()
    }

    stockout_risk_count = 0
    replenishment_requirement = 0.0
    inventory_cost = 0.0

    for inv in inventory_rows:
        adjusted_avg_demand = avg_daily_demand(db, inv.product_id, inv.warehouse_id) * demand_multiplier
        adjusted_safety_stock = inv.safety_stock * safety_multiplier
        lead_time = max(1, inv.product.lead_time_days + params.lead_time_delta_days)

        # --- stockout risk: same shape as analyze_inventory_item() (Phase 2) ---
        days_of_inventory = (inv.on_hand / adjusted_avg_demand) if adjusted_avg_demand > 0 else None
        safety_days = (
            max(1, round(adjusted_safety_stock / adjusted_avg_demand))
            if adjusted_avg_demand > 0
            else adjusted_safety_stock
        )
        if days_of_inventory is not None and days_of_inventory <= (lead_time + safety_days):
            stockout_risk_count += 1

        # --- replenishment requirement + inventory cost: same shape as replenishment_service.py (Phase 6) ---
        forecast = forecasts_by_pair.get((inv.product_id, inv.warehouse_id))
        forecast_demand = _forecast_demand_over_days(forecast, lead_time, demand_multiplier)
        recommended = max(forecast_demand + adjusted_safety_stock - inv.on_hand - inv.incoming_qty, 0.0)
        replenishment_requirement += recommended
        inventory_cost += recommended * float(inv.product.unit_cost)

    # --- late shipments: same shape as effective_status()/compute_delay_days() (Phase 3) ---
    late_shipments_count = 0
    active_shipments = (
        db.query(Shipment)
        .filter(Shipment.workspace_id == workspace_id, Shipment.status.notin_([DELIVERED, CANCELLED]))
        .all()
    )
    for shipment in active_shipments:
        real_delay = compute_delay_days(shipment)
        scenario_delay = max(0, real_delay + params.shipment_delay_delta_days)
        if scenario_delay > 0:
            late_shipments_count += 1

    total_pairs = len(inventory_rows) or 1
    service_level_pct = round(100 * (1 - stockout_risk_count / total_pairs), 1)

    return {
        "stockout_risk_count": stockout_risk_count,
        "late_shipments_count": late_shipments_count,
        "service_level_pct": service_level_pct,
        "inventory_cost": round(inventory_cost, 2),
        "replenishment_requirement": round(replenishment_requirement, 2),
    }


def compute_comparison(db: Session, workspace_id: int, params: ScenarioParams) -> dict:
    """Baseline (all deltas zero) vs simulated (the given params), plus deltas."""
    baseline = _compute_metrics(db, workspace_id, ScenarioParams())
    simulated = _compute_metrics(db, workspace_id, params)
    delta = {key: round(simulated[key] - baseline[key], 2) for key in baseline}
    return {"baseline": baseline, "simulated": simulated, "delta": delta}


def create_and_run_scenario(db: Session, workspace_id: int, name: str, params: ScenarioParams) -> SimulationScenario:
    """Persist the scenario + both results — for scenarios worth naming and revisiting."""
    scenario = SimulationScenario(
        workspace_id=workspace_id,
        name=name,
        demand_change_pct=params.demand_change_pct,
        lead_time_delta_days=params.lead_time_delta_days,
        shipment_delay_delta_days=params.shipment_delay_delta_days,
        safety_stock_change_pct=params.safety_stock_change_pct,
    )
    db.add(scenario)
    db.flush()

    comparison = compute_comparison(db, workspace_id, params)
    _persist_results(db, scenario.id, comparison)

    db.commit()
    db.refresh(scenario)
    return scenario


def rerun_scenario(db: Session, scenario: SimulationScenario) -> dict:
    """Re-execute an existing saved scenario against CURRENT real data and store a fresh result pair.

    Real data drifts (shipments get delivered, forecasts regenerate) —
    re-running shows how the same hypothetical looks today, not just at
    the moment it was first saved.
    """
    params = ScenarioParams(
        demand_change_pct=scenario.demand_change_pct,
        lead_time_delta_days=scenario.lead_time_delta_days,
        shipment_delay_delta_days=scenario.shipment_delay_delta_days,
        safety_stock_change_pct=scenario.safety_stock_change_pct,
    )
    comparison = compute_comparison(db, scenario.workspace_id, params)
    _persist_results(db, scenario.id, comparison)
    db.commit()
    return comparison


def _persist_results(db: Session, scenario_id: int, comparison: dict) -> None:
    for is_baseline, key in ((True, "baseline"), (False, "simulated")):
        metrics = comparison[key]
        db.add(
            SimulationResult(
                scenario_id=scenario_id,
                is_baseline=is_baseline,
                stockout_risk_count=metrics["stockout_risk_count"],
                late_shipments_count=metrics["late_shipments_count"],
                service_level_pct=metrics["service_level_pct"],
                inventory_cost=metrics["inventory_cost"],
                replenishment_requirement=metrics["replenishment_requirement"],
            )
        )
