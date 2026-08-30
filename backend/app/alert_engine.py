"""
Alert Engine — Phase 4.

Six rule-based checks, each returning a list of currently-triggered
conditions. `generate_alerts()` reconciles those against what's already in
the `alerts` table:

- A triggered condition with no existing OPEN/ACKNOWLEDGED alert -> new
  Alert row (status=OPEN).
- A triggered condition that already has an OPEN/ACKNOWLEDGED alert ->
  that row's severity/description are refreshed in place (no duplicate
  row created).
- An existing OPEN/ACKNOWLEDGED alert whose condition did NOT trigger this
  run -> auto-resolved (status=RESOLVED, resolved_at=now). E.g. a shipment
  that was delayed and has since been delivered no longer needs an alert.

This intentionally reuses calculations from earlier phases rather than
recomputing them: STOCKOUT_RISK reuses analyze_inventory_item() (Phase 2),
SHIPMENT_DELAY reuses effective_status()/compute_delay_days() (Phase 3).
The alert engine's own job is just "decide what's alert-worthy and turn it
into a persistent, actionable record" — not re-deriving numbers that
already exist elsewhere.
"""
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from .inventory_analysis import analyze_inventory_item
from .models import Alert, AlertSeverity, AlertStatus, AlertType, DemandRecord, Inventory, Shipment, Supplier
from .shipment_service import DELAYED, DELIVERED, compute_delay_days, effective_status

# --- thresholds (kept as named constants so they're easy to find/tune) ---

STOCKOUT_CRITICAL_DAYS = 2.0  # days_of_inventory at/below this -> CRITICAL instead of WARNING
SHIPMENT_DELAY_CRITICAL_DAYS = 5  # delay_days at/above this -> CRITICAL instead of WARNING

SUPPLIER_MIN_SAMPLE = 3  # don't judge a supplier on fewer than this many delivered shipments
SUPPLIER_LATE_RATE_WARNING = 0.30
SUPPLIER_LATE_RATE_CRITICAL = 0.50

DEMAND_SPIKE_RECENT_DAYS = 7
DEMAND_SPIKE_BASELINE_DAYS = 21  # the 21 days immediately before the recent window
DEMAND_SPIKE_WARNING_MULTIPLIER = 1.5
DEMAND_SPIKE_CRITICAL_MULTIPLIER = 2.0
DEMAND_SPIKE_MIN_BASELINE = 1.0  # avoid flagging near-zero-demand SKUs as "spiking"


TriggeredCondition = dict[str, Any]


def _check_low_stock_and_critical_stock(db: Session, workspace_id: int) -> list[TriggeredCondition]:
    triggered = []
    for inv in db.query(Inventory).filter(Inventory.workspace_id == workspace_id).all():
        label = f"{inv.product.sku} at {inv.warehouse.code}"
        if inv.on_hand <= inv.safety_stock:
            triggered.append(
                {
                    "alert_type": AlertType.CRITICAL_STOCK,
                    "severity": AlertSeverity.CRITICAL,
                    "title": f"Critical stock: {label}",
                    "description": (
                        f"On hand ({inv.on_hand}) is at or below safety stock "
                        f"({inv.safety_stock}) for {inv.product.name}."
                    ),
                    "related_entity_type": "inventory",
                    "related_entity_id": inv.id,
                    "related_entity_label": label,
                }
            )
        elif inv.on_hand <= inv.reorder_point:
            triggered.append(
                {
                    "alert_type": AlertType.LOW_STOCK,
                    "severity": AlertSeverity.WARNING,
                    "title": f"Low stock: {label}",
                    "description": (
                        f"On hand ({inv.on_hand}) is at or below the reorder point "
                        f"({inv.reorder_point}) for {inv.product.name}."
                    ),
                    "related_entity_type": "inventory",
                    "related_entity_id": inv.id,
                    "related_entity_label": label,
                }
            )
    return triggered


def _check_stockout_risk(db: Session, workspace_id: int) -> list[TriggeredCondition]:
    triggered = []
    for inv in db.query(Inventory).filter(Inventory.workspace_id == workspace_id).all():
        analysis = analyze_inventory_item(db, inv)
        if not analysis["stockout_risk"]:
            continue
        days = analysis["days_of_inventory"]
        label = f"{inv.product.sku} at {inv.warehouse.code}"
        severity = AlertSeverity.CRITICAL if days is not None and days <= STOCKOUT_CRITICAL_DAYS else AlertSeverity.WARNING
        days_text = f"{days} days" if days is not None else "an unknown number of days (no recent demand data)"
        triggered.append(
            {
                "alert_type": AlertType.STOCKOUT_RISK,
                "severity": severity,
                "title": f"Stockout risk: {label}",
                "description": f"Projected stockout in {days_text}.",
                "related_entity_type": "inventory",
                "related_entity_id": inv.id,
                "related_entity_label": label,
            }
        )
    return triggered


def _check_shipment_delay(db: Session, workspace_id: int) -> list[TriggeredCondition]:
    triggered = []
    for shipment in db.query(Shipment).filter(Shipment.workspace_id == workspace_id).all():
        if effective_status(shipment) != DELAYED:
            continue
        delay_days = compute_delay_days(shipment)
        severity = AlertSeverity.CRITICAL if delay_days >= SHIPMENT_DELAY_CRITICAL_DAYS else AlertSeverity.WARNING
        triggered.append(
            {
                "alert_type": AlertType.SHIPMENT_DELAY,
                "severity": severity,
                "title": f"Shipment delayed: {shipment.shipment_number}",
                "description": (
                    f"{shipment.shipment_number} ({shipment.product.sku} -> {shipment.warehouse.code}) "
                    f"is {delay_days} day(s) past its ETA of {shipment.eta_date}."
                ),
                "related_entity_type": "shipment",
                "related_entity_id": shipment.id,
                "related_entity_label": shipment.shipment_number,
            }
        )
    return triggered


def _check_supplier_delay(db: Session, workspace_id: int) -> list[TriggeredCondition]:
    triggered = []
    for supplier in db.query(Supplier).filter(Supplier.workspace_id == workspace_id).all():
        delivered = [s for s in supplier.shipments if s.status == DELIVERED]
        if len(delivered) < SUPPLIER_MIN_SAMPLE:
            continue
        late_count = sum(1 for s in delivered if compute_delay_days(s) > 0)
        late_rate = late_count / len(delivered)
        if late_rate < SUPPLIER_LATE_RATE_WARNING:
            continue
        severity = AlertSeverity.CRITICAL if late_rate >= SUPPLIER_LATE_RATE_CRITICAL else AlertSeverity.WARNING
        triggered.append(
            {
                "alert_type": AlertType.SUPPLIER_DELAY,
                "severity": severity,
                "title": f"Supplier delay pattern: {supplier.name}",
                "description": (
                    f"{late_count} of {len(delivered)} recent deliveries ({late_rate:.0%}) "
                    f"from {supplier.name} arrived late."
                ),
                "related_entity_type": "supplier",
                "related_entity_id": supplier.id,
                "related_entity_label": supplier.name,
            }
        )
    return triggered


def _check_demand_spike(db: Session, workspace_id: int) -> list[TriggeredCondition]:
    triggered = []
    today = date.today()
    recent_start = today - timedelta(days=DEMAND_SPIKE_RECENT_DAYS)
    baseline_start = recent_start - timedelta(days=DEMAND_SPIKE_BASELINE_DAYS)

    for inv in db.query(Inventory).filter(Inventory.workspace_id == workspace_id).all():
        recent_total = (
            db.query(DemandRecord)
            .filter(
                DemandRecord.product_id == inv.product_id,
                DemandRecord.warehouse_id == inv.warehouse_id,
                DemandRecord.record_date >= recent_start,
                DemandRecord.record_date < today,
            )
            .with_entities(DemandRecord.demand_qty)
            .all()
        )
        baseline_total = (
            db.query(DemandRecord)
            .filter(
                DemandRecord.product_id == inv.product_id,
                DemandRecord.warehouse_id == inv.warehouse_id,
                DemandRecord.record_date >= baseline_start,
                DemandRecord.record_date < recent_start,
            )
            .with_entities(DemandRecord.demand_qty)
            .all()
        )
        if not recent_total or not baseline_total:
            continue

        recent_avg = sum(r[0] for r in recent_total) / len(recent_total)
        baseline_avg = sum(r[0] for r in baseline_total) / len(baseline_total)
        if baseline_avg < DEMAND_SPIKE_MIN_BASELINE:
            continue

        ratio = recent_avg / baseline_avg
        if ratio < DEMAND_SPIKE_WARNING_MULTIPLIER:
            continue

        label = f"{inv.product.sku} at {inv.warehouse.code}"
        severity = AlertSeverity.CRITICAL if ratio >= DEMAND_SPIKE_CRITICAL_MULTIPLIER else AlertSeverity.WARNING
        pct_increase = round((ratio - 1) * 100)
        triggered.append(
            {
                "alert_type": AlertType.DEMAND_SPIKE,
                "severity": severity,
                "title": f"Demand spike: {label}",
                "description": (
                    f"Recent {DEMAND_SPIKE_RECENT_DAYS}-day avg demand ({recent_avg:.1f}/day) is "
                    f"{pct_increase}% above the prior {DEMAND_SPIKE_BASELINE_DAYS}-day baseline "
                    f"({baseline_avg:.1f}/day)."
                ),
                "related_entity_type": "inventory",
                "related_entity_id": inv.id,
                "related_entity_label": label,
            }
        )
    return triggered


_ALL_CHECKS = (
    _check_low_stock_and_critical_stock,
    _check_stockout_risk,
    _check_shipment_delay,
    _check_supplier_delay,
    _check_demand_spike,
)


def _dedupe_key(condition: TriggeredCondition) -> str:
    return f"{condition['alert_type'].value}:{condition['related_entity_type']}:{condition['related_entity_id']}"


def generate_alerts(db: Session, workspace_id: int) -> dict[str, int]:
    """Run every rule, open/refresh alerts for what's currently true, and
    auto-resolve alerts for conditions that are no longer true. Safe to call
    repeatedly (e.g. on every dashboard load or app startup) — idempotent
    in the sense that it never creates duplicate OPEN alerts for the same
    condition.
    """
    triggered_conditions: list[TriggeredCondition] = []
    for check in _ALL_CHECKS:
        triggered_conditions.extend(check(db, workspace_id))

    triggered_by_key = {_dedupe_key(c): c for c in triggered_conditions}

    existing_active = (
        db.query(Alert)
        .filter(Alert.workspace_id == workspace_id, Alert.status.in_([AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED]))
        .all()
    )
    existing_by_key = {alert.dedupe_key: alert for alert in existing_active}

    created = 0
    refreshed = 0
    resolved = 0
    now = datetime.utcnow()

    for key, condition in triggered_by_key.items():
        existing = existing_by_key.get(key)
        if existing is None:
            db.add(
                Alert(
                    workspace_id=workspace_id,
                    alert_type=condition["alert_type"],
                    severity=condition["severity"],
                    title=condition["title"],
                    description=condition["description"],
                    related_entity_type=condition["related_entity_type"],
                    related_entity_id=condition["related_entity_id"],
                    related_entity_label=condition["related_entity_label"],
                    status=AlertStatus.OPEN,
                    dedupe_key=key,
                )
            )
            created += 1
        else:
            if existing.severity != condition["severity"] or existing.description != condition["description"]:
                existing.severity = condition["severity"]
                existing.description = condition["description"]
                existing.title = condition["title"]
                refreshed += 1

    for key, alert in existing_by_key.items():
        if key not in triggered_by_key:
            alert.status = AlertStatus.RESOLVED
            alert.resolved_at = now
            resolved += 1

    db.commit()
    return {"created": created, "refreshed": refreshed, "resolved": resolved, "active": len(triggered_by_key)}
