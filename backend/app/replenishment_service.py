"""
Replenishment Recommendation — Phase 6.

Formula, straight from AGENTS.md section 11:

    Recommended Order = max(
        Forecast Demand + Safety Stock - Current Stock - Incoming Stock,
        0
    )

The one design decision AGENTS.md leaves open is what "Forecast Demand"
means concretely — over what time window? The natural answer, and the one
used here: the demand expected to occur during the product's lead time,
i.e. the window between placing a reorder and it actually arriving. That's
exactly what a replenishment quantity needs to cover. So:

    Forecast Demand = sum of Phase 5's estimated_demand for the next
                       product.lead_time_days days

This is a direct, explainable use of Phase 5's output (not a re-derived
average) — the same "reuse the earlier phase's calculation" pattern as
the alert engine (STOCKOUT_RISK reuses analyze_inventory_item(),
SHIPMENT_DELAY reuses effective_status()).

Lead time source: Product.lead_time_days, not Supplier.lead_time_days.
A single Inventory row (product, warehouse) isn't tied to one supplier —
shipments for the same product come from whichever supplier was used for
that particular order (see seed.py) — so there's no single "the" supplier
lead time for a (product, warehouse) pair to anchor this on. Product's own
lead_time_days is the stable, per-SKU baseline already used elsewhere in
the app for exactly this purpose.
"""
from sqlalchemy.orm import Session

from .models import Forecast, Inventory, Product, ReplenishmentRecommendation, Warehouse


def _forecast_demand_over_lead_time(forecast: Forecast, lead_time_days: int) -> float:
    points = sorted(forecast.points, key=lambda p: p.day_offset)[:lead_time_days]
    return sum(p.estimated_demand for p in points)


def _build_explanation(
    lead_time_days: int,
    forecast_demand: float,
    safety_stock: int,
    on_hand: int,
    incoming_qty: int,
    recommended_quantity: float,
) -> str:
    raw = forecast_demand + safety_stock - on_hand - incoming_qty
    return (
        f"Forecast demand over the next {lead_time_days}-day lead time is "
        f"{forecast_demand:.1f} units. Recommended order = max(forecast demand + "
        f"safety stock - on hand - incoming, 0) = max({forecast_demand:.1f} + "
        f"{safety_stock} - {on_hand} - {incoming_qty}, 0) = max({raw:.1f}, 0) = "
        f"{recommended_quantity:.1f}."
    )


def generate_recommendation_for_pair(
    db: Session, product: Product, warehouse: Warehouse, inventory: Inventory
) -> ReplenishmentRecommendation | None:
    forecast = (
        db.query(Forecast)
        .filter(Forecast.product_id == product.id, Forecast.warehouse_id == warehouse.id)
        .first()
    )
    if forecast is None:
        # No Phase 5 forecast yet for this pair (e.g. insufficient demand
        # history) — can't compute Forecast Demand, so skip rather than
        # guessing. Run POST /forecasts/generate first for this pair.
        return None

    forecast_demand = _forecast_demand_over_lead_time(forecast, product.lead_time_days)
    recommended_quantity = max(
        forecast_demand + inventory.safety_stock - inventory.on_hand - inventory.incoming_qty,
        0.0,
    )
    explanation = _build_explanation(
        product.lead_time_days, forecast_demand, inventory.safety_stock, inventory.on_hand, inventory.incoming_qty, recommended_quantity
    )

    existing = (
        db.query(ReplenishmentRecommendation)
        .filter(
            ReplenishmentRecommendation.product_id == product.id,
            ReplenishmentRecommendation.warehouse_id == warehouse.id,
        )
        .first()
    )
    if existing is not None:
        db.delete(existing)
        db.flush()

    recommendation = ReplenishmentRecommendation(
        workspace_id=product.workspace_id,
        product_id=product.id,
        warehouse_id=warehouse.id,
        lead_time_days=product.lead_time_days,
        forecast_demand=round(forecast_demand, 2),
        safety_stock=inventory.safety_stock,
        current_stock=inventory.on_hand,
        incoming_stock=inventory.incoming_qty,
        recommended_quantity=round(recommended_quantity, 2),
        explanation=explanation,
    )
    db.add(recommendation)
    db.commit()
    db.refresh(recommendation)
    return recommendation


def generate_all_recommendations(db: Session, workspace_id: int) -> dict:
    generated = 0
    skipped = 0
    for inventory in db.query(Inventory).filter(Inventory.workspace_id == workspace_id).all():
        result = generate_recommendation_for_pair(db, inventory.product, inventory.warehouse, inventory)
        if result is None:
            skipped += 1
        else:
            generated += 1
    return {"generated": generated, "skipped_no_forecast": skipped}
