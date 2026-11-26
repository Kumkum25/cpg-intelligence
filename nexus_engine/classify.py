"""Demand classification: ADI/CV2, confidence, trend, seasonality, regime shift.

Classification thresholds (ADI < 1.32, CV2 < 0.49) and the K>=8 confidence
rule both come straight from the golden fixtures in the README (§5):

    SMOOTH        ADI < 1.32  and CV2 < 0.49
    ERRATIC       ADI < 1.32  and CV2 >= 0.49
    INTERMITTENT  ADI >= 1.32 and CV2 < 0.49
    LUMPY         ADI >= 1.32 and CV2 >= 0.49

Population variance (ddof=0) is used throughout, matching
``answer_key/quick_check_90d.csv``'s stated method.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

ADI_THRESHOLD = 1.32
CV2_THRESHOLD = 0.49
HIGH_CONFIDENCE_K = 8


def _window_profile(g: pd.DataFrame, window_days: int, asof: pd.Timestamp) -> pd.Series:
    """ADI/CV2 class + confidence for one store/sku series already filtered
    to valid days within the window. ``g`` must have columns
    ['date', 'sold_ea', 'stockout_flag'].
    """
    y = g["sold_ea"].to_numpy(dtype=float)
    N = len(y)
    z = y[y > 0]
    K = len(z)

    # History completeness: is there even enough *calendar* history behind
    # asof to fill this window, independent of how much of it was valid?
    # (NRG-NEW-250 only has 51 days of life at all, so neither its 90D nor
    # 365D window can ever be "complete" — confidence must reflect that even
    # if K looks fine.)
    earliest_possible = asof - pd.Timedelta(days=window_days - 1)
    first_date_in_data = g["date"].min() if N else pd.NaT
    window_complete = N > 0 and first_date_in_data <= earliest_possible

    if N == 0:
        # Not ranged (or no valid days at all) in this window — e.g. a
        # delisted SKU like COL-CLS-330. This is NOT the same as DORMANT:
        # dormant means "ranged, reporting, zero demand"; this means "there
        # was nothing to observe at all."
        return pd.Series(dict(
            N=0, K=0, velocity=np.nan, adi=np.nan, cv2=np.nan,
            demand_class="NOT_RANGED", confidence="NOT_APPLICABLE", window_complete=False,
        ))

    if K == 0:
        return pd.Series(dict(
            N=N, K=0, velocity=0.0, adi=np.nan, cv2=np.nan,
            demand_class="DORMANT", confidence="NOT_APPLICABLE", window_complete=window_complete,
        ))

    adi = N / K
    if K < 2:
        # A single positive observation can't support a variance estimate.
        demand_class = "INSUFFICIENT"
        cv2 = np.nan
    else:
        cv2 = float(z.var(ddof=0) / z.mean() ** 2)
        if adi < ADI_THRESHOLD and cv2 < CV2_THRESHOLD:
            demand_class = "SMOOTH"
        elif adi < ADI_THRESHOLD:
            demand_class = "ERRATIC"
        elif cv2 < CV2_THRESHOLD:
            demand_class = "INTERMITTENT"
        else:
            demand_class = "LUMPY"

    if demand_class == "INSUFFICIENT":
        confidence = "PROVISIONAL"
    elif not window_complete:
        confidence = "PROVISIONAL"
    else:
        confidence = "HIGH" if K >= HIGH_CONFIDENCE_K else "PROVISIONAL"

    return pd.Series(dict(
        N=N, K=K, velocity=round(float(y.mean()), 3), adi=round(adi, 3),
        cv2=(round(cv2, 4) if cv2 == cv2 else np.nan),  # NaN-safe round
        demand_class=demand_class, confidence=confidence, window_complete=window_complete,
    ))


def _trend_direction(g: pd.DataFrame, slope_threshold: float = 0.08) -> tuple[str, float]:
    """OLS slope of sold_ea on day-index, normalized by the series mean so
    the threshold is scale-free. Needs >=14 valid days to say anything.
    """
    y = g.sort_values("date")["sold_ea"].to_numpy(dtype=float)
    n = len(y)
    if n < 14 or y.mean() == 0:
        return "STABLE", 0.0
    x = np.arange(n, dtype=float)
    slope = float(np.polyfit(x, y, 1)[0])
    relative_slope = slope * n / y.mean()  # total % move across the window
    if relative_slope > slope_threshold:
        return "INCREASING", relative_slope
    if relative_slope < -slope_threshold:
        return "DECLINING", relative_slope
    return "STABLE", relative_slope


def _seasonality_strength(g: pd.DataFrame, by: str) -> float:
    """Eta-squared (share of variance explained) of demand grouped by
    ``by`` in {'dow', 'month'} — a 0..1 "how seasonal is this" score. Needs
    a reasonable amount of history to mean anything (caller gates on N).
    """
    y = g["sold_ea"].to_numpy(dtype=float)
    if y.var(ddof=0) == 0 or len(y) < 28:
        return 0.0
    key = g["date"].dt.day_of_week if by == "dow" else g["date"].dt.month
    grand_mean = y.mean()
    total_ss = ((y - grand_mean) ** 2).sum()
    between_ss = 0.0
    for _, idx in pd.Series(np.arange(len(y))).groupby(key.to_numpy()):
        grp = y[idx.to_numpy()]
        between_ss += len(grp) * (grp.mean() - grand_mean) ** 2
    return float(between_ss / total_ss) if total_ss > 0 else 0.0


def profile_window(panel: pd.DataFrame, asof: pd.Timestamp, window_days: int) -> pd.DataFrame:
    """Per store/sku ADI/CV2 profile restricted to [asof - window_days + 1, asof]."""
    start = asof - pd.Timedelta(days=window_days - 1)
    w = panel[(panel["date"] >= start) & (panel["date"] <= asof) & panel["valid_day"]]

    rows = []
    for (store_id, sku_code), g in w.groupby(["store_id", "sku_code"]):
        prof = _window_profile(g, window_days, asof)
        trend, trend_score = _trend_direction(g)
        oos_days = int(g["stockout_flag"].sum())
        rows.append({
            "store_id": store_id, "sku_code": sku_code, "window_days": window_days,
            **prof.to_dict(), "trend_direction": trend, "trend_score": round(trend_score, 3),
            "oos_days": oos_days,
        })
    # Series ranged-but-entirely-outside-window (e.g. delisted before the
    # window even starts) never appear in `w` via groupby, so backfill them
    # as NOT_RANGED from the full scope list.
    all_series = panel[["store_id", "sku_code"]].drop_duplicates()
    out = all_series.merge(pd.DataFrame(rows), on=["store_id", "sku_code"], how="left")
    missing = out["demand_class"].isna()
    out.loc[missing, ["N", "K"]] = 0
    out.loc[missing, "demand_class"] = "NOT_RANGED"
    out.loc[missing, "confidence"] = "NOT_APPLICABLE"
    out.loc[missing, "window_days"] = window_days
    out.loc[missing, "window_complete"] = False
    out.loc[missing, "trend_direction"] = "STABLE"
    out.loc[missing, "oos_days"] = 0
    return out


def seasonality_profile(panel: pd.DataFrame) -> pd.DataFrame:
    """Weekly/annual seasonality strength computed over each series' full
    available valid-day history (not window-scoped — seasonality needs the
    long run to be visible at all).
    """
    rows = []
    for (store_id, sku_code), g in panel[panel["valid_day"]].groupby(["store_id", "sku_code"]):
        weekly = _seasonality_strength(g, "dow")
        annual = _seasonality_strength(g, "month") if (g["date"].max() - g["date"].min()).days >= 300 else np.nan
        rows.append({
            "store_id": store_id, "sku_code": sku_code,
            "weekly_seasonality_strength": round(weekly, 3),
            "annual_seasonality_strength": (round(annual, 3) if annual == annual else np.nan),
            "history_days": int(len(g)),
        })
    return pd.DataFrame(rows)


def regime_shift_flags(profile_90d: pd.DataFrame, profile_365d: pd.DataFrame) -> pd.DataFrame:
    """Flags series whose short-window classification disagrees with the
    long-window one — a signal the demand pattern itself has changed, not
    just noise (e.g. SNK-BAR-40: SMOOTH over 365D, INTERMITTENT over 90D).
    """
    m = profile_90d[["store_id", "sku_code", "demand_class"]].merge(
        profile_365d[["store_id", "sku_code", "demand_class"]],
        on=["store_id", "sku_code"], suffixes=("_90d", "_365d"),
    )
    comparable = {"SMOOTH", "ERRATIC", "INTERMITTENT", "LUMPY"}
    m["regime_shift_detected"] = (
        m["demand_class_90d"].isin(comparable)
        & m["demand_class_365d"].isin(comparable)
        & (m["demand_class_90d"] != m["demand_class_365d"])
    )
    return m[["store_id", "sku_code", "demand_class_90d", "demand_class_365d", "regime_shift_detected"]]
