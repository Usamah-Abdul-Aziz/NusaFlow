"""
Demand Forecasting — Phase 5.

Pipeline, matching the progression in AGENTS.md section 11 exactly:

    Historical Data -> Data Cleaning -> Feature Engineering ->
    Baseline Model -> Forecast -> Evaluation

  1. Historical Data — `_load_daily_series()` pulls DemandRecord rows for
     one (product, warehouse) pair.
  2. Data Cleaning — the same function fills any missing calendar days
     with 0 rather than silently skipping them, so a moving average isn't
     quietly computed over a shorter/misaligned window than intended.
  3. Feature Engineering — `_weekday_factors()` turns "day of week" into
     a learned multiplier (e.g. Sunday demand is typically ~0.6x an
     average day) from real history, not a guess.
  4. Baseline Model — two candidates, both intentionally simple per
     AGENTS.md section 8 ("prioritize baseline models... do not use
     complex ML models merely to make the project sound more advanced"):
       - moving_average: flat forecast = avg of the last N days.
       - weekday_seasonal: recent-trend level x that day's weekday factor.
  5. Forecast — the winning model (see Evaluation) is re-fit on the FULL
     history and projected forward `horizon_days` days.
  6. Evaluation — `_backtest()` holds out the last 14 real days, forecasts
     over that same window using data before it, and scores each
     candidate model with MAE/MAPE against what actually happened. The
     model with the lower MAE is the one used for the real forecast, and
     its backtest error is what's reported alongside it — so the
     confidence numbers describe real historical performance, not a
     hardcoded guess.

No pandas/numpy/scikit-learn: at this data scale (~240 points per pair)
plain Python is simpler to read, has zero extra dependencies, and is
exactly as fast as this needs to be — consistent with the "don't add a
dependency unless it's actually necessary" rule in AGENTS.md section 23.
"""
import statistics
from datetime import date, timedelta

from sqlalchemy.orm import Session

from .models import DemandRecord, Forecast, ForecastMethod, ForecastPoint, Inventory, Product, Warehouse

BACKTEST_HOLDOUT_DAYS = 14
TREND_WINDOW_DAYS = 14  # "recent level" window used by both models
LOOKBACK_DAYS = 180  # how much history to pull per pair
DEFAULT_HORIZON_DAYS = 30

DailySeries = list[tuple[date, float]]


# --- 1 & 2: Historical Data + Data Cleaning ---------------------------------


def _load_daily_series(db: Session, product_id: int, warehouse_id: int, lookback_days: int = LOOKBACK_DAYS) -> DailySeries:
    start = date.today() - timedelta(days=lookback_days)
    rows = (
        db.query(DemandRecord.record_date, DemandRecord.demand_qty)
        .filter(
            DemandRecord.product_id == product_id,
            DemandRecord.warehouse_id == warehouse_id,
            DemandRecord.record_date >= start,
            DemandRecord.record_date < date.today(),
        )
        .all()
    )
    by_date = {r.record_date: r.demand_qty for r in rows}
    if not by_date:
        return []

    first_day = min(by_date)
    last_day = max(by_date)
    series: DailySeries = []
    current = first_day
    while current <= last_day:
        # Missing calendar day -> treat as 0 demand rather than skipping it,
        # so downstream windows (moving average, weekday factors) stay
        # aligned to real calendar days instead of silently compressing.
        series.append((current, float(by_date.get(current, 0))))
        current += timedelta(days=1)
    return series


# --- 3: Feature Engineering --------------------------------------------------


def _weekday_factors(series: DailySeries) -> dict[int, float]:
    """weekday (0=Monday..6=Sunday) -> multiplier vs the overall daily average."""
    if not series:
        return {i: 1.0 for i in range(7)}

    overall_avg = sum(v for _, v in series) / len(series)
    if overall_avg <= 0:
        return {i: 1.0 for i in range(7)}

    by_weekday: dict[int, list[float]] = {i: [] for i in range(7)}
    for day, value in series:
        by_weekday[day.weekday()].append(value)

    factors = {}
    for weekday, values in by_weekday.items():
        factors[weekday] = (sum(values) / len(values)) / overall_avg if values else 1.0
    return factors


def _recent_level(series: DailySeries, window: int = TREND_WINDOW_DAYS) -> float:
    """Average demand over the most recent `window` days — the "current level" both models scale from."""
    if not series:
        return 0.0
    tail = series[-window:] if len(series) >= window else series
    return sum(v for _, v in tail) / len(tail)


# --- 4: Baseline Models -------------------------------------------------------


def _moving_average_forecast(series: DailySeries, horizon_days: int, start_date: date) -> list[float]:
    level = _recent_level(series)
    return [level for _ in range(horizon_days)]


def _weekday_seasonal_forecast(series: DailySeries, horizon_days: int, start_date: date) -> list[float]:
    level = _recent_level(series)
    factors = _weekday_factors(series)
    return [max(0.0, level * factors.get((start_date + timedelta(days=i)).weekday(), 1.0)) for i in range(horizon_days)]


_MODELS = {
    ForecastMethod.MOVING_AVERAGE: _moving_average_forecast,
    ForecastMethod.WEEKDAY_SEASONAL: _weekday_seasonal_forecast,
}


# --- 6: Evaluation (done before the final Forecast step, so its result can pick the model) ---


def _backtest(series: DailySeries, method: ForecastMethod) -> dict:
    """Fit on everything except the last BACKTEST_HOLDOUT_DAYS real days,
    forecast that same window, and score against what actually happened.
    """
    if len(series) <= BACKTEST_HOLDOUT_DAYS + TREND_WINDOW_DAYS:
        # Not enough history for a meaningful holdout — caller should skip.
        return {"mae": None, "mape": None, "residual_std": None}

    train = series[:-BACKTEST_HOLDOUT_DAYS]
    holdout = series[-BACKTEST_HOLDOUT_DAYS:]
    holdout_start = holdout[0][0]

    predicted = _MODELS[method](train, len(holdout), holdout_start)
    actual = [v for _, v in holdout]

    residuals = [a - p for a, p in zip(actual, predicted)]
    abs_errors = [abs(r) for r in residuals]
    mae = sum(abs_errors) / len(abs_errors)

    # MAPE is undefined (division by zero) on any day with zero actual
    # demand — common for slow-moving SKUs — so skip those days rather
    # than reporting a misleading number.
    pct_errors = [abs(r) / a for r, a in zip(residuals, actual) if a > 0]
    mape = (sum(pct_errors) / len(pct_errors) * 100) if pct_errors else None

    residual_std = statistics.pstdev(residuals) if len(residuals) > 1 else abs_errors[0]

    return {"mae": mae, "mape": mape, "residual_std": residual_std}


def _choose_method(series: DailySeries) -> tuple[ForecastMethod, dict]:
    """Backtest every candidate model, return whichever has the lower MAE."""
    scored = []
    for method in _MODELS:
        result = _backtest(series, method)
        if result["mae"] is not None:
            scored.append((method, result))

    if not scored:
        # Not enough history to backtest at all — fall back to the
        # simplest possible model with an honest "we don't really know" band.
        level = _recent_level(series)
        fallback_std = statistics.pstdev([v for _, v in series]) if len(series) > 1 else level
        return ForecastMethod.MOVING_AVERAGE, {"mae": None, "mape": None, "residual_std": fallback_std}

    scored.sort(key=lambda pair: pair[1]["mae"])
    return scored[0]


# --- 5: Forecast (re-fit chosen model on full history) + persistence ---------


def generate_forecast_for_pair(db: Session, product: Product, warehouse: Warehouse, horizon_days: int = DEFAULT_HORIZON_DAYS) -> Forecast | None:
    series = _load_daily_series(db, product.id, warehouse.id)
    if len(series) < TREND_WINDOW_DAYS:
        return None  # not enough history yet to say anything useful

    method, eval_result = _choose_method(series)
    today = date.today()
    predicted_values = _MODELS[method](series, horizon_days, today)
    residual_std = eval_result["residual_std"] or 0.0

    # Replace any previous forecast for this pair rather than accumulating.
    existing = (
        db.query(Forecast)
        .filter(Forecast.product_id == product.id, Forecast.warehouse_id == warehouse.id)
        .first()
    )
    if existing is not None:
        db.delete(existing)
        db.flush()

    forecast = Forecast(
        workspace_id=product.workspace_id,
        product_id=product.id,
        warehouse_id=warehouse.id,
        method=method,
        horizon_days=horizon_days,
        mae=eval_result["mae"] if eval_result["mae"] is not None else 0.0,
        mape=eval_result["mape"],
        residual_std=residual_std,
    )
    db.add(forecast)
    db.flush()

    for i, value in enumerate(predicted_values, start=1):
        db.add(
            ForecastPoint(
                forecast_id=forecast.id,
                forecast_date=today + timedelta(days=i - 1),
                day_offset=i,
                estimated_demand=round(value, 2),
                # Naive but honest uncertainty band from backtest residual
                # spread, widening slightly further out since errors
                # compound the further ahead you project.
                lower_bound=round(max(0.0, value - residual_std * (1 + i / horizon_days)), 2),
                upper_bound=round(value + residual_std * (1 + i / horizon_days), 2),
            )
        )

    db.commit()
    db.refresh(forecast)
    return forecast


def generate_all_forecasts(db: Session, workspace_id: int, horizon_days: int = DEFAULT_HORIZON_DAYS) -> dict:
    generated = 0
    skipped = 0
    for inv in db.query(Inventory).filter(Inventory.workspace_id == workspace_id).all():
        result = generate_forecast_for_pair(db, inv.product, inv.warehouse, horizon_days)
        if result is None:
            skipped += 1
        else:
            generated += 1
    return {"generated": generated, "skipped_insufficient_history": skipped}
