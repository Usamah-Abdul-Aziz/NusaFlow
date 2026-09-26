"""
Shipment domain logic — Phase 3 (Real-Time Shipment Monitoring).

Two responsibilities live here, both kept out of main.py on purpose:

1. Real delay/status calculation. `delay_days` and `status` stored on the
   Shipment row are only updated when the lifecycle actually advances
   (see `advance_shipment`). Between advances, time keeps passing — so a
   shipment that was "in_transit" yesterday can already be overdue today
   even though nobody touched the database. `effective_status()` and
   `compute_delay_days()` derive the *current* truth by comparing stored
   dates against today, instead of trusting a number that was only
   correct at seed/advance time.

2. A lightweight, deterministic simulation. There is no background
   worker/cron here on purpose — this project must run on free-tier
   hosting where a long-lived scheduler process isn't guaranteed to stay
   alive. Instead, `advance_shipment` moves a shipment one step through
   its lifecycle each time it's called (e.g. from a "Simulate update"
   button in the UI). The next step is fully determined by the shipment's
   event history and current dates, so calling it twice with the same
   state always produces the same result (deterministic / testable),
   while the actual path taken (whether a delay gets detected) still
   varies naturally per shipment because it depends on real eta dates.
"""
from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from .models import Shipment, ShipmentEvent, ShipmentStatus

# Kept as short local aliases so the branching logic below stays readable.
PENDING = ShipmentStatus.PENDING
IN_TRANSIT = ShipmentStatus.IN_TRANSIT
DELAYED = ShipmentStatus.DELAYED
DELIVERED = ShipmentStatus.DELIVERED
CANCELLED = ShipmentStatus.CANCELLED

# Statuses that no longer change on their own — the journey is over.
_TERMINAL_STATUSES = (DELIVERED, CANCELLED)


def effective_status(shipment: Shipment, today: Optional[date] = None) -> str:
    """The shipment's true current status, accounting for elapsed time.

    A shipment stored as "in_transit" that has quietly sailed past its
    eta_date without being delivered IS late, whether or not anyone has
    run the simulation since then. This function is what makes that
    visible without needing a scheduler to "notice" in real time.
    """
    today = today or date.today()

    if shipment.status in _TERMINAL_STATUSES or shipment.status == PENDING:
        return shipment.status

    # status is "in_transit" or already "delayed": recheck against today.
    if today > shipment.eta_date:
        return DELAYED
    return IN_TRANSIT


def compute_delay_days(shipment: Shipment, today: Optional[date] = None) -> int:
    """Real delay in days, computed from dates rather than trusted from a stored int."""
    today = today or date.today()

    if shipment.status == CANCELLED:
        return 0

    if shipment.status == DELIVERED and shipment.actual_delivery_date:
        return max(0, (shipment.actual_delivery_date - shipment.eta_date).days)

    if shipment.status == PENDING:
        return 0

    # in transit (or previously marked delayed) and not yet delivered
    if today > shipment.eta_date:
        return (today - shipment.eta_date).days
    return 0


def serialize_shipment_state(shipment: Shipment, today: Optional[date] = None) -> dict:
    """Live status + delay for a shipment, safe to merge into any response dict."""
    return {
        "status": effective_status(shipment, today),
        "delay_days": compute_delay_days(shipment, today),
    }


def get_events(db: Session, shipment_id: int) -> list[ShipmentEvent]:
    return (
        db.query(ShipmentEvent)
        .filter(ShipmentEvent.shipment_id == shipment_id)
        .order_by(ShipmentEvent.event_time.asc(), ShipmentEvent.id.asc())
        .all()
    )


class ShipmentAlreadyTerminalError(Exception):
    """Raised when trying to advance a shipment that has already delivered/cancelled."""


# Manual shipments get their own numbering range (SH-M####) so they can
# never collide with a seeded SH-1#### number, now or after a re-seed.
_MANUAL_PREFIX = "SH-M"


def _next_shipment_number(db: Session, workspace_id: int) -> str:
    """The next unused manual shipment number for this workspace.

    current-max + 1 rather than a row count: deletes would otherwise let a
    count drift below a surviving max and hand out a number that already
    exists, breaking the per-workspace unique constraint.
    """
    numbers = (
        db.query(Shipment.shipment_number)
        .filter(Shipment.workspace_id == workspace_id, Shipment.shipment_number.like(f"{_MANUAL_PREFIX}%"))
        .all()
    )
    highest = 0
    for (number,) in numbers:
        suffix = number[len(_MANUAL_PREFIX) :]
        if suffix.isdigit():
            highest = max(highest, int(suffix))
    return f"{_MANUAL_PREFIX}{highest + 1:04d}"


def create_shipment(
    db: Session,
    workspace_id: int,
    *,
    product,
    warehouse,
    supplier,
    quantity: int,
    eta_date: date,
    status: ShipmentStatus = ShipmentStatus.PENDING,
) -> Shipment:
    """Create one shipment row, already compatible with the rest of Phase 3.

    The caller (main.py) has already verified that product/warehouse/supplier
    all belong to this workspace. Two things here matter for that
    compatibility:

    - status defaults to PENDING, and "Shipment Created" is written as the
      first event. advance_shipment's state machine decides the next step
      from the LAST event, so a shipment with no Created event could never
      take its first step ("Simulate next step" in the UI would read an
      empty history and jump straight to Departed without a departure).
      This mirrors exactly what seed.py writes for every seeded shipment.
    - delay_days starts at 0 and status/delay are never guessed here —
      effective_status()/compute_delay_days() derive the live truth from
      dates, exactly as they do for seeded shipments.

    eta_date is passed in, not computed here, because the caller decides
    whether the user gave an absolute date or a transit-day lead time.
    """
    now = datetime.utcnow()
    shipment = Shipment(
        workspace_id=workspace_id,
        shipment_number=_next_shipment_number(db, workspace_id),
        product_id=product.id,
        warehouse_id=warehouse.id,
        supplier_id=supplier.id,
        quantity=quantity,
        eta_date=eta_date,
        status=status,
        delay_days=0,
        created_at=now,
    )
    shipment.events = [ShipmentEvent(shipment_id=None, event_type="Shipment Created", event_time=now, details="Manually created shipment")]
    db.add(shipment)
    db.commit()
    db.refresh(shipment)
    return shipment


def advance_shipment(db: Session, shipment: Shipment) -> ShipmentEvent:
    """Move a shipment one step forward in its lifecycle and return the new event.

    Sequence: Shipment Created -> Shipment Departed -> (Checkpoint Reached |
    Delay Detected) -> (Delay Detected ->) Shipment Delivered.

    Whether "Delay Detected" appears depends on whether the shipment is
    actually past its eta_date at the moment this is called — real dates
    drive the branch, not randomness.
    """
    if shipment.status in _TERMINAL_STATUSES:
        raise ShipmentAlreadyTerminalError(
            f"Shipment {shipment.shipment_number} is already {shipment.status}"
        )

    events = get_events(db, shipment.id)
    last_type = events[-1].event_type if events else None
    now = datetime.utcnow()
    today = now.date()
    is_late = today > shipment.eta_date

    if last_type is None or last_type == "Shipment Created":
        shipment.status = IN_TRANSIT
        new_event = ShipmentEvent(
            shipment_id=shipment.id,
            event_type="Shipment Departed",
            event_time=now,
            details="Outbound dispatch confirmed",
        )

    elif last_type == "Shipment Departed":
        if is_late:
            shipment.status = DELAYED
            new_event = ShipmentEvent(
                shipment_id=shipment.id,
                event_type="Delay Detected",
                event_time=now,
                details=f"Shipment is {(today - shipment.eta_date).days} day(s) past its ETA",
            )
        else:
            new_event = ShipmentEvent(
                shipment_id=shipment.id,
                event_type="Checkpoint Reached",
                event_time=now,
                details="Shipment passed an intermediate checkpoint",
            )

    elif last_type == "Checkpoint Reached":
        if is_late:
            shipment.status = DELAYED
            new_event = ShipmentEvent(
                shipment_id=shipment.id,
                event_type="Delay Detected",
                event_time=now,
                details=f"Shipment is {(today - shipment.eta_date).days} day(s) past its ETA",
            )
        else:
            shipment.status = DELIVERED
            shipment.actual_delivery_date = today
            shipment.delay_days = compute_delay_days(shipment, today)
            new_event = ShipmentEvent(
                shipment_id=shipment.id,
                event_type="Shipment Delivered",
                event_time=now,
                details="Delivered on schedule",
            )

    elif last_type == "Delay Detected":
        shipment.status = DELIVERED
        shipment.actual_delivery_date = today
        shipment.delay_days = compute_delay_days(shipment, today)
        new_event = ShipmentEvent(
            shipment_id=shipment.id,
            event_type="Shipment Delivered",
            event_time=now,
            details=f"Delivered {shipment.delay_days} day(s) late",
        )

    else:
        # Unknown/legacy event type — fall back to delivering the shipment
        # rather than getting stuck.
        shipment.status = DELIVERED
        shipment.actual_delivery_date = today
        shipment.delay_days = compute_delay_days(shipment, today)
        new_event = ShipmentEvent(
            shipment_id=shipment.id,
            event_type="Shipment Delivered",
            event_time=now,
            details="Delivered",
        )

    db.add(new_event)
    db.commit()
    db.refresh(shipment)
    db.refresh(new_event)
    return new_event
