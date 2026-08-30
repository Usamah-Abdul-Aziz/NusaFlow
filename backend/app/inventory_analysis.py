from datetime import date, timedelta
from typing import Dict, Any
import time

from sqlalchemy.orm import Session
from sqlalchemy import func

from .config import get_settings
from .models import DemandRecord, Inventory, Product, Warehouse

# Simple in-memory TTL cache for avg_daily_demand
_CACHE: Dict[str, tuple[float, float]] = {}


def _cache_ttl_seconds() -> int:
    return get_settings().CACHE_TTL


def _cache_key(product_id: int, warehouse_id: int, window_days: int) -> str:
    start_date = date.today() - timedelta(days=window_days)
    return f"{product_id}:{warehouse_id}:{window_days}:{start_date.isoformat()}"


def avg_daily_demand(db: Session, product_id: int, warehouse_id: int, window_days: int = 30) -> float:
    """Calculate average daily demand over the past window_days for the given product and warehouse.

    Uses a small TTL cache keyed by (product_id, warehouse_id, window_days, start_date) so repeated
    calls during the same day/window are fast. The cache is intentionally simple and in-memory; for
    larger deployments replace with Redis or another shared cache.
    """
    key = _cache_key(product_id, warehouse_id, window_days)
    now = time.time()
    cached = _CACHE.get(key)
    if cached:
        value, fetched_at = cached
        if now - fetched_at < _cache_ttl_seconds():
            return value

    start_date = date.today() - timedelta(days=window_days)
    q = (
        db.query(func.sum(DemandRecord.demand_qty).label("total"))
        .filter(DemandRecord.product_id == product_id)
        .filter(DemandRecord.warehouse_id == warehouse_id)
        .filter(DemandRecord.record_date >= start_date)
    ).one()
    total = q.total or 0
    value = float(total) / max(window_days, 1)

    _CACHE[key] = (value, now)
    return value


def clear_cache() -> None:
    """Clear the in-memory demand cache."""
    global _CACHE
    _CACHE.clear()


def analyze_inventory_item(db: Session, inv: Inventory, window_days: int = 30) -> Dict[str, Any]:
    """Return analysis for a single inventory row including avg demand and days of inventory."""
    avg_demand = avg_daily_demand(db, inv.product_id, inv.warehouse_id, window_days)
    days_of_inventory = None
    if avg_demand > 0:
        days_of_inventory = round(inv.on_hand / avg_demand, 2)

    stockout_risk = False
    # Simple rule: stockout risk if days_of_inventory exists and is less than product lead time + safety buffer
    lead_time = inv.product.lead_time_days if getattr(inv.product, 'lead_time_days', None) else 0
    safety_days = max(1, round(inv.safety_stock / max(avg_demand, 1))) if avg_demand > 0 else inv.safety_stock

    if days_of_inventory is not None and days_of_inventory <= (lead_time + safety_days):
        stockout_risk = True

    return {
        "id": inv.id,
        "sku": inv.product.sku,
        "product": inv.product.name,
        "warehouse": inv.warehouse.code,
        "on_hand": inv.on_hand,
        "safety_stock": inv.safety_stock,
        "reorder_point": inv.reorder_point,
        "incoming_qty": inv.incoming_qty,
        "avg_daily_demand": round(avg_demand, 2),
        "days_of_inventory": days_of_inventory,
        "stockout_risk": stockout_risk,
    }


def analyze_inventory(db: Session, workspace_id: int, window_days: int = 30, sku: str | None = None, warehouse: str | None = None, page: int = 1, page_size: int = 20):
    """Return paginated inventory analysis. Supports optional filters: sku and warehouse code.

    Returns a dict with items and pagination metadata.
    """
    query = db.query(Inventory).join(Product).join(Warehouse).filter(Inventory.workspace_id == workspace_id)
    if sku:
        query = query.filter(Product.sku == sku)
    if warehouse:
        query = query.filter(Warehouse.code == warehouse)

    total = query.count()
    page = max(1, int(page))
    page_size = max(1, int(page_size))
    offset = (page - 1) * page_size

    items = query.offset(offset).limit(page_size).all()
    results = [analyze_inventory_item(db, inv, window_days) for inv in items]
    total_pages = (total + page_size - 1) // page_size

    return {
        "items": results,
        "pagination": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        },
    }
