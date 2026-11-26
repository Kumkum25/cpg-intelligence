"""Valid-day logic — traps #6, #7, #8, #9 from the README.

Builds one row per (store_id, sku_code, date) across the full history for
every series that is ever ranged, and classifies each day as:

    CLOSED       store_open = False                    -> excluded from N
    MISSING      store_open, feed not received/complete -> excluded from N
    NOT_RANGED   store open+fed, but SKU not ranged     -> excluded from N
                 that store on that date (pre-launch / post-delist)
    CONFIRMED_ZERO  valid day, no POS line for the SKU  -> in N, not in K
    SALE            valid day, sold_ea > 0              -> in N and in K

Only ``feed_complete`` gates validity: in this dataset it is always equal to
``pos_feed_received`` (both flip together on outage days), and it is the one
the README calls the "completeness contract" for confirmed zeros.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .ingest import RawData


def _series_scope(ranging: pd.DataFrame, asof: pd.Timestamp) -> pd.DataFrame:
    """One row per ranged store/sku interval, with an open-ended ``ranged_to``
    filled in as ``asof`` (still ranged as of the analysis date).
    """
    scope = ranging.copy()
    scope["ranged_to_eff"] = scope["ranged_to"].fillna(asof)
    return scope


def build_daily_panel(raw: RawData, daily_demand: pd.DataFrame, asof: pd.Timestamp) -> pd.DataFrame:
    """Full store x sku x date panel with validity/status and joined sales.

    ``daily_demand`` is the gross-demand table from :func:`clean.build_daily_demand`.
    """
    cal = raw.calendar[["store_id", "date", "store_open", "pos_feed_received", "feed_complete"]]
    scope = _series_scope(raw.ranging, asof)

    panels = []
    for row in scope.itertuples(index=False):
        store_dates = cal[cal["store_id"] == row.store_id][["date"]].drop_duplicates()
        store_dates = store_dates[(store_dates["date"] >= row.ranged_from) & (store_dates["date"] <= row.ranged_to_eff)]
        if store_dates.empty:
            continue
        p = store_dates.copy()
        p["store_id"] = row.store_id
        p["sku_code"] = row.sku_code
        panels.append(p)

    if not panels:
        return pd.DataFrame(columns=["store_id", "sku_code", "date", "day_status", "valid_day", "sold_ea", "is_confirmed_zero"])

    panel = pd.concat(panels, ignore_index=True)
    panel = panel.merge(cal, on=["store_id", "date"], how="left")
    panel = panel.merge(daily_demand[["store_id", "sku_code", "date", "sold_ea"]], on=["store_id", "sku_code", "date"], how="left")
    panel["sold_ea"] = panel["sold_ea"].fillna(0.0)

    feed_ok = panel["pos_feed_received"].fillna(False) & panel["feed_complete"].fillna(False)
    conditions = [
        ~panel["store_open"].fillna(False),
        panel["store_open"].fillna(False) & ~feed_ok,
    ]
    choices = ["CLOSED", "MISSING"]
    panel["day_status"] = np.select(conditions, choices, default="")
    panel.loc[panel["day_status"] == "", "day_status"] = np.where(
        panel.loc[panel["day_status"] == "", "sold_ea"] > 0, "SALE", "CONFIRMED_ZERO"
    )

    panel["valid_day"] = ~panel["day_status"].isin(["CLOSED", "MISSING"])
    panel["is_confirmed_zero"] = panel["day_status"] == "CONFIRMED_ZERO"

    # Trap #10: stockouts. Observed sales on an OOS day are censored demand,
    # not a true signal of appetite — surfaced as a flag, not a classification
    # override (the engine still counts what was actually sold).
    inv = raw.inventory_daily.rename(columns={"inventory_date": "date"})[["store_id", "sku_code", "date", "on_hand_eod_ea", "oos_eod_flag"]]
    panel = panel.merge(inv, on=["store_id", "sku_code", "date"], how="left")
    panel["stockout_flag"] = panel["oos_eod_flag"].fillna(False)

    cols = ["store_id", "sku_code", "date", "day_status", "valid_day", "is_confirmed_zero", "sold_ea", "stockout_flag", "on_hand_eod_ea"]
    return panel[cols].sort_values(["sku_code", "store_id", "date"]).reset_index(drop=True)
