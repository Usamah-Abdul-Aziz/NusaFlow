"""
Demand history backfill — closes the "empty workspace" gap (CLAUDE.md 4a).

Forecasting, replenishment, the DEMAND_SPIKE alert and the what-if
simulation all need demand history, which until now could only enter the
system through the seed script. A workspace created via signup could add
warehouses, products and stock, then hit "not enough demand history yet"
on every downstream feature.

The user supplies one rough number — "about N units leave per day" — and we
expand it into a plausible daily series using the SAME weekday + noise
variation the seed script uses (seed.estimated_daily_demand), so an
estimated pair is statistically shaped like the demo data rather than
following some second, subtly different generator. Every generated row is
flagged is_estimated=True, which the forecast/replenishment endpoints
surface as a yellow "this is an estimate" badge.

Days that already have a demand record for the pair are left untouched —
the estimate never overwrites history that might be real.
"""
import random
from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from .models import DemandRecord
from .seed import estimated_daily_demand, mean_weekday_factor

# Enough history for forecast_service's 14-day backtest + trend window with
# plenty of margin. Not the full 240 days seed.py writes — a user
# backfilling by hand is asking "when can I try forecasting?", and 90 days
# answers that immediately without making them wait on 240 rows per pair.
DEFAULT_ESTIMATE_DAYS = 90

# Below ~30 days the forecast backtest has too little to hold out and
# generate_forecast_for_pair still returns None.
MIN_ESTIMATE_DAYS = 30
MAX_ESTIMATE_DAYS = 400

QuickEstimateResult = dict[str, Any]


def _estimate_rng(
    product_id: int,
    warehouse_id: int,
    avg_units_per_day: float,
    days_back: int,
) -> random.Random:
    """A seeded RNG per (pair, rate, window).

    Seeded instead of random() so that re-running the estimate for the same
    pair with the same number reproduces the same history — the numbers a
    forecast was built on don't silently reshuffle when someone clicks the
    button twice — while different pairs still get unrelated sequences.
    The seed is a string because random.Random() only accepts scalars (not
    tuples); a string seed is encoded to bytes, so it's stable across
    processes unlike hash() of a str under PYTHONHASHSEED.
    """
    return random.Random(f"{product_id}:{warehouse_id}:{round(avg_units_per_day, 3)}:{days_back}")


def generate_quick_estimate(
    db: Session,
    product,
    warehouse,
    avg_units_per_day: float,
    days_back: int = DEFAULT_ESTIMATE_DAYS,
    today: date | None = None,
) -> QuickEstimateResult:
    """Expand `avg_units_per_day` into `days_back` days of estimated demand
    history for one (product, warehouse) pair, inserting only the days that
    don't already have a record. Returns a summary the endpoint hands back
    to the caller verbatim.
    """
    today = today or date.today()

    # The user's number is an average across the whole week; weekends run
    # at 0.6x, so a flat base rate would average ~11% under it. Dividing
    # by the pattern's mean makes the generated history honor the number
    # the user actually typed.
    base_rate = avg_units_per_day / mean_weekday_factor()
    rng = _estimate_rng(product.id, warehouse.id, avg_units_per_day, days_back)

    start = today - timedelta(days=days_back)
    # History ends yesterday: forecast_service only reads rows strictly
    # before today, and today isn't a complete day of demand yet.
    end = today - timedelta(days=1)

    existing_dates = {
        row[0]
        for row in db.query(DemandRecord.record_date)
        .filter(
            DemandRecord.product_id == product.id,
            DemandRecord.warehouse_id == warehouse.id,
            DemandRecord.record_date >= start,
            DemandRecord.record_date <= end,
        )
        .all()
    }

    rows: list[dict[str, Any]] = []
    day = start
    while day <= end:
        if day not in existing_dates:
            rows.append(
                {
                    "product_id": product.id,
                    "warehouse_id": warehouse.id,
                    "record_date": day,
                    "demand_qty": estimated_daily_demand(base_rate, day, rng),
                    "is_estimated": True,
                }
            )
        day += timedelta(days=1)

    if rows:
        db.bulk_insert_mappings(DemandRecord, rows)
        db.commit()

    return {
        "days_generated": len(rows),
        "days_skipped_existing": len(existing_dates),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "avg_units_per_day": avg_units_per_day,
        "is_estimated": True,
    }
