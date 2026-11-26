"""Top-level forecasting orchestrator: series prep -> model comparison ->
selection -> refit -> future forecast. This is the one entry point the API
and frontend call; nothing above this needs to know how any individual
model works.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .backtest import compare_models, recommend_model
from .metrics import all_metrics
from .models import MODEL_REGISTRY
from .selector import shortlist_models

FREQ_SEASON_LENGTH = {"D": 7, "W": 52, "M": 12}
FREQ_PANDAS = {"D": "D", "W": "W-MON", "M": "MS"}


@dataclass
class ForecastResult:
    store_id: str
    sku_code: str
    frequency: str
    horizon: int
    demand_class: str
    candidate_models: list[str]
    comparison: list[dict]
    selected_model: str
    selected_by: str  # "auto_recommended" | "user_selected"
    history_dates: list[str]
    history_actual: list[float]
    forecast_dates: list[str]
    forecast_values: list[float]
    interval_kind: str | None
    forecast_lower: list[float] | None
    forecast_upper: list[float] | None
    trend: str
    summary: str
    warnings: list[str] = field(default_factory=list)


def build_series(panel: pd.DataFrame, store_id: str, sku_code: str, frequency: str) -> pd.Series:
    """Valid-day demand only (closures/outages/not-ranged days are excluded,
    not zero-filled — same convention as the demand profiler), then
    resampled to the requested frequency.
    """
    g = panel[(panel["store_id"] == store_id) & (panel["sku_code"] == sku_code) & panel["valid_day"]].sort_values("date")
    s = pd.Series(g["sold_ea"].to_numpy(), index=pd.DatetimeIndex(g["date"]))
    if frequency == "D":
        return s
    rule = FREQ_PANDAS[frequency]
    return s.resample(rule).sum()


def run_forecast(
    panel: pd.DataFrame,
    demand_profile: pd.DataFrame,
    store_id: str,
    sku_code: str,
    horizon: int = 30,
    frequency: str = "D",
    model_override: str | None = None,
    n_folds: int = 3,
) -> ForecastResult:
    if frequency not in FREQ_SEASON_LENGTH:
        raise ValueError(f"Unsupported frequency {frequency!r}; use one of {list(FREQ_SEASON_LENGTH)}")

    season_length = FREQ_SEASON_LENGTH[frequency]
    series = build_series(panel, store_id, sku_code, frequency)
    y = series.to_numpy(dtype=float)
    warnings: list[str] = []

    row = demand_profile[(demand_profile["store_id"] == store_id) & (demand_profile["sku_code"] == sku_code)]
    if len(row) == 0:
        raise ValueError(f"{sku_code} at {store_id} is not a known series in this demand profile.")
    demand_class = row["demand_class_365d"].iloc[0]
    current_class = row["demand_class_90d"].iloc[0]

    # Gate on *current* rangedness (90D), not the long-run class: a SKU can
    # have had perfectly SMOOTH demand for two years right up to the day it
    # was delisted (e.g. COL-CLS-330) — 365D still calls that SMOOTH, but
    # there is nothing to forecast forward for a product no longer ranged.
    if "is_discontinued" in row.columns and bool(row["is_discontinued"].iloc[0]):
        raise ValueError(f"{sku_code} at {store_id} has been discontinued (past its delist date) — nothing to forecast forward, even though some of the trailing 90-day window still has sales history.")
    if current_class == "NOT_RANGED" or len(y) == 0:
        raise ValueError(f"{sku_code} at {store_id} is not currently ranged (no valid demand in the last 90 days) — nothing to forecast forward.")

    candidates = shortlist_models(demand_class, len(y))
    comparison = compare_models(y, candidates, horizon, season_length, n_folds=n_folds)

    auto_pick = recommend_model(comparison)
    if model_override:
        if model_override not in MODEL_REGISTRY:
            raise ValueError(f"Unknown model {model_override!r}. Choose from {list(MODEL_REGISTRY)}")
        selected, selected_by = model_override, "user_selected"
    elif auto_pick:
        selected, selected_by = auto_pick, "auto_recommended"
    else:
        selected, selected_by = "naive", "auto_recommended"
        warnings.append("No candidate model produced a usable backtest score (too little history) — falling back to Naive.")

    spec = MODEL_REGISTRY[selected]
    if len(y) < spec.min_train_length:
        warnings.append(f"{spec.factory().name} normally needs >= {spec.min_train_length} points; only {len(y)} available. Forecast may be unreliable.")

    model = spec.factory().fit(y, season_length)
    point = model.predict(horizon)
    point = np.clip(point, 0, None)

    interval = None
    interval_kind = model.interval_kind
    try:
        interval = model.predict_interval(horizon)
    except Exception:
        interval = None
        interval_kind = None
    lower, upper = (None, None) if interval is None else (np.clip(interval[0], 0, None).tolist(), interval[1].tolist())

    last_date = series.index[-1] if len(series) else pd.Timestamp.today()
    future_dates = pd.date_range(last_date, periods=horizon + 1, freq=FREQ_PANDAS[frequency])[1:]

    recent_mean = float(np.mean(y[-min(len(y), season_length):])) if len(y) else 0.0
    forecast_mean = float(np.mean(point)) if len(point) else 0.0
    if recent_mean == 0 and forecast_mean == 0:
        trend = "FLAT"
    elif recent_mean == 0:
        trend = "INCREASING"
    else:
        rel = (forecast_mean - recent_mean) / recent_mean
        trend = "INCREASING" if rel > 0.08 else "DECLINING" if rel < -0.08 else "STABLE"

    best_metrics = next((c["metrics"] for c in comparison if c["model_key"] == selected), None)
    summary = (
        f"{sku_code} at {store_id}: demand is classified {demand_class} (365D). "
        f"{'Recommended' if selected_by == 'auto_recommended' else 'User-selected'} model: {spec.factory().name}"
        + (f" (WAPE {best_metrics['wape']:.1%} on backtest)" if best_metrics and best_metrics.get("wape") is not None else "")
        + f". Forecast trend over the next {horizon} {('days' if frequency=='D' else 'weeks' if frequency=='W' else 'months')}: {trend.lower()}."
    )

    return ForecastResult(
        store_id=store_id, sku_code=sku_code, frequency=frequency, horizon=horizon,
        demand_class=demand_class, candidate_models=candidates, comparison=comparison,
        selected_model=selected, selected_by=selected_by,
        history_dates=[d.strftime("%Y-%m-%d") for d in series.index],
        history_actual=[round(v, 3) for v in y.tolist()],
        forecast_dates=[d.strftime("%Y-%m-%d") for d in future_dates],
        forecast_values=[round(v, 3) for v in point.tolist()],
        interval_kind=interval_kind,
        forecast_lower=([round(v, 3) for v in lower] if lower is not None else None),
        forecast_upper=([round(v, 3) for v in upper] if upper is not None else None),
        trend=trend, summary=summary, warnings=warnings,
    )
