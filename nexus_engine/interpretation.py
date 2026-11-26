"""Plain-language interpretation of a demand profile row, plus the
new-product / discontinued-product flags. Kept separate from classify.py
(pure statistics) so the business-language layer can evolve independently
of the classification math.
"""
from __future__ import annotations

import pandas as pd

NEW_PRODUCT_WINDOW_DAYS = 180


def zero_sales_frequency(N, K) -> float | None:
    """Share of valid days with no sales at all. None when there were no
    valid days to begin with (NOT_RANGED) rather than a misleading 0 or 1.
    """
    if not N:
        return None
    return round(1 - (K / N), 4)


def product_status_flags(launch_date, delist_date, asof: pd.Timestamp) -> dict:
    is_new = bool(pd.notna(launch_date) and (asof - pd.Timestamp(launch_date)).days <= NEW_PRODUCT_WINDOW_DAYS)
    is_discontinued = bool(pd.notna(delist_date) and pd.Timestamp(delist_date) <= asof)
    return {"is_new_product": is_new, "is_discontinued": is_discontinued}


def business_interpretation(row: dict) -> str:
    """One sentence a category manager could read without knowing what ADI
    or CV² mean. ``row`` is one record from the demand_profile table
    (90D columns), plus is_new_product/is_discontinued.
    """
    cls = row.get("demand_class_90d")
    N, K = row.get("N_90d"), row.get("K_90d")
    adi, cv2 = row.get("adi_90d"), row.get("cv2_90d")
    conf = row.get("confidence_90d")
    trend = row.get("trend_direction_90d")
    zero_freq = row.get("zero_sales_frequency_90d")

    if row.get("is_discontinued"):
        return "This product has been discontinued (past its delist date) — no forward demand profile applies."
    if cls == "NOT_RANGED":
        return "Not currently ranged at this store — no valid selling days in the last 90 days."
    if cls == "DORMANT":
        return f"Ranged and reporting for {N:.0f} days, but zero sales in that window — flagged DORMANT rather than simply low-volume."
    if cls in ("INSUFFICIENT", None):
        k_txt = f"{K:.0f}" if K is not None else "0"
        return f"Only {k_txt} positive-demand day(s) observed — too little data to estimate variability reliably."

    trend_txt = {"INCREASING": "trending up", "DECLINING": "trending down", "STABLE": "holding steady"}.get(trend, "")
    new_txt = " This is a recently launched product, so its profile will firm up with more history." if row.get("is_new_product") else ""
    conf_txt = "a solid sample" if conf == "HIGH" else "a thin sample — treat as provisional"

    base = {
        "SMOOTH": f"Sells {'frequently and predictably' if adi is not None else 'regularly'} (ADI {adi:.2f}, CV² {cv2:.2f}); demand is {trend_txt}.",
        "ERRATIC": f"Sells frequently but order sizes vary a lot (ADI {adi:.2f}, CV² {cv2:.2f}) — hard to plan tight safety stock.",
        "INTERMITTENT": f"Sells on roughly 1 in {adi:.1f} valid days, with consistent order sizes when it does (CV² {cv2:.2f}); "
                         f"{zero_freq:.0%} of days see no sales." if zero_freq is not None else f"Intermittent demand (ADI {adi:.2f}).",
        "LUMPY": f"Both infrequent and highly variable when it does sell (ADI {adi:.2f}, CV² {cv2:.2f}) — the hardest pattern to forecast tightly.",
    }.get(cls, f"Classified {cls}.")

    return f"{base} Confidence is {conf} ({conf_txt}).{new_txt}"
