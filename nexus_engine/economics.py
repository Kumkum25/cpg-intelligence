"""Economic profiling — traps #11 through #17 from the README.

    11. Overlapping price intervals        -> flagged, never silently "latest wins"
    12. Missing COGS                        -> GM/GM% NULL with a reason, never treated as 0
    13. Price change mid-history             -> joined on the effective date
    14. MOQ in CS vs EA                      -> converted to EA before coverage math
    15. Two suppliers, one SKU                -> kept as separate rows, never averaged
    16. Missing inventory valuation           -> GMROI NULL with INVENTORY_VALUATION_MISSING
    17. Short shelf life vs MOQ                -> flagged as a potential-surplus risk
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .ingest import RawData


def _flag_overlaps(econ: pd.DataFrame) -> pd.DataFrame:
    """Trap #11: mark every row that overlaps another row for the same
    sku_code + channel_id. An open-ended ``effective_to`` (still active)
    overlaps anything that starts after it.
    """
    econ = econ.sort_values(["sku_code", "channel_id", "effective_from"]).copy()
    econ["_to_sort"] = econ["effective_to"].fillna(pd.Timestamp("2200-01-01"))
    econ["overlaps"] = False
    for _, g in econ.groupby(["sku_code", "channel_id"]):
        idx = g.index.to_numpy()
        ends = g["_to_sort"].to_numpy()
        starts = g["effective_from"].to_numpy()
        for i in range(len(idx)):
            for j in range(i + 1, len(idx)):
                if starts[j] <= ends[i]:
                    econ.loc[idx[i], "overlaps"] = True
                    econ.loc[idx[j], "overlaps"] = True
    return econ.drop(columns=["_to_sort"])


def price_cogs_for_date(econ_flagged: pd.DataFrame, sku_code: str, channel_id: str, date: pd.Timestamp) -> dict:
    """Trap #11 + #13: look up the effective price/COGS for one sku/channel/date.

    Returns a dict with net_price_per_ea, cogs_per_ea, and a `pricing_issue`
    reason (None, 'PRICE_CONFLICT', or 'NO_PRICE_ON_DATE').
    """
    rows = econ_flagged[
        (econ_flagged["sku_code"] == sku_code)
        & (econ_flagged["channel_id"] == channel_id)
        & (econ_flagged["effective_from"] <= date)
        & (econ_flagged["effective_to"].isna() | (econ_flagged["effective_to"] >= date))
    ]
    if len(rows) == 0:
        return {"net_price_per_ea": np.nan, "cogs_per_ea": np.nan, "pricing_issue": "NO_PRICE_ON_DATE"}
    if len(rows) > 1:
        # Never silently take the latest: surface the conflict, but still
        # report the most-recently-effective row's values so GM can be
        # computed where it's safe to, with the issue visible alongside it.
        chosen = rows.sort_values("effective_from").iloc[-1]
        return {"net_price_per_ea": chosen["net_price_per_ea"], "cogs_per_ea": chosen["cogs_per_ea"], "pricing_issue": "PRICE_CONFLICT"}
    r = rows.iloc[0]
    return {"net_price_per_ea": r["net_price_per_ea"], "cogs_per_ea": r["cogs_per_ea"], "pricing_issue": None}


def economics_summary(raw: RawData, demand_profile_90d: pd.DataFrame, asof: pd.Timestamp) -> pd.DataFrame:
    """Per store/sku economics as of ``asof``: price, COGS, GM/GM%, and
    GMROI built off the 90D demand profile's velocity.
    """
    econ_flagged = _flag_overlaps(raw.sku_economics)
    # Sku-level flag: does this SKU's price history contain an overlap
    # *anywhere*, independent of whether asof happens to fall inside it?
    # TEA-RTD-500's conflict is Mar-May 2026 — a snapshot taken today looks
    # clean, but the underlying data problem is still there and worth
    # surfacing rather than only catching it if asof happens to land on it.
    has_overlap = econ_flagged.groupby(["sku_code", "channel_id"])["overlaps"].any()
    loc = raw.location[["store_id", "channel"]]

    rows = []
    for row in demand_profile_90d.itertuples(index=False):
        store_id, sku_code, velocity = row.store_id, row.sku_code, getattr(row, "velocity", np.nan)
        channel = loc.loc[loc["store_id"] == store_id, "channel"].iloc[0]
        pc = price_cogs_for_date(econ_flagged, sku_code, channel, asof)
        price_history_has_overlap = bool(has_overlap.get((sku_code, channel), False))

        gm_per_ea, gm_pct, gm_issue = np.nan, np.nan, None
        if pc["pricing_issue"] == "PRICE_CONFLICT":
            gm_issue = "PRICE_CONFLICT"
        elif pc["pricing_issue"] == "NO_PRICE_ON_DATE":
            gm_issue = "NO_PRICE_ON_DATE"
        elif pd.isna(pc["cogs_per_ea"]):
            gm_issue = "MISSING_COGS"  # trap #12 — never defaulted to 0
        elif pd.isna(pc["net_price_per_ea"]):
            gm_issue = "NO_PRICE_ON_DATE"
        else:
            gm_per_ea = pc["net_price_per_ea"] - pc["cogs_per_ea"]
            gm_pct = gm_per_ea / pc["net_price_per_ea"] if pc["net_price_per_ea"] else np.nan

        rows.append({
            "store_id": store_id, "sku_code": sku_code,
            "net_price_per_ea": pc["net_price_per_ea"], "cogs_per_ea": pc["cogs_per_ea"],
            "pricing_issue": pc["pricing_issue"], "price_history_has_overlap": price_history_has_overlap,
            "gm_per_ea": (round(gm_per_ea, 4) if gm_per_ea == gm_per_ea else np.nan),
            "gm_pct": (round(gm_pct, 4) if gm_pct == gm_pct else np.nan), "gm_issue": gm_issue,
            "velocity_90d": velocity,
        })
    return pd.DataFrame(rows)


def gmroi_summary(raw: RawData, econ: pd.DataFrame, asof: pd.Timestamp, lookback_days: int = 90) -> pd.DataFrame:
    """Trap #16: GMROI = annualized GM$ / average inventory value at cost
    over the trailing weekly snapshots. NULL with a reason when valuation
    data is missing rather than silently dropped or zeroed.
    """
    val = raw.inventory_valuation_weekly
    start = asof - pd.Timedelta(days=lookback_days)
    recent = val[(val["inventory_date"] > start) & (val["inventory_date"] <= asof) & (val["snapshot_status"] == "FINAL")]
    avg_val = recent.groupby(["store_id", "sku_code"])["inventory_value_at_cost"].mean().rename("avg_inventory_value_at_cost")

    out = econ.merge(avg_val, on=["store_id", "sku_code"], how="left")
    annualized_units = out["velocity_90d"] * 365
    annualized_gm = annualized_units * out["gm_per_ea"]

    gmroi = pd.Series(np.nan, index=out.index)
    reason = pd.Series(None, index=out.index, dtype=object)

    no_val_rows = out["avg_inventory_value_at_cost"].isna()
    zero_val = out["avg_inventory_value_at_cost"] == 0
    has_val = ~no_val_rows & ~zero_val
    has_gm = out["gm_per_ea"].notna()

    reason[no_val_rows] = "INVENTORY_VALUATION_MISSING"  # no snapshot at all in the lookback — trap #16
    reason[zero_val] = "ZERO_INVENTORY_VALUE"  # snapshots exist but carry $0 (e.g. depleted delisted stock)
    reason[has_val & ~has_gm] = out.loc[has_val & ~has_gm, "gm_issue"]
    computable = has_val & has_gm
    gmroi[computable] = annualized_gm[computable] / out.loc[computable, "avg_inventory_value_at_cost"]

    out["avg_inventory_value_at_cost"] = out["avg_inventory_value_at_cost"].round(2)
    out["annualized_gm"] = annualized_gm.round(2)
    out["gmroi"] = gmroi.round(3)
    out["gmroi_issue"] = reason
    return out


def supplier_summary(raw: RawData, demand_profile_90d: pd.DataFrame, asof: pd.Timestamp) -> pd.DataFrame:
    """Trap #14/#15/#17: MOQ normalized to EA, kept per-supplier (never
    averaged across suppliers of the same SKU), with a coverage-days and
    shelf-life-risk read against the SKU's current velocity.
    """
    sc = raw.supplier_constraints
    active = sc[(sc["effective_from"] <= asof) & (sc["effective_to"].isna() | (sc["effective_to"] >= asof))].copy()
    active["moq_ea"] = active["moq_qty"] * active["eaches_per_uom"]

    vel = demand_profile_90d[["store_id", "sku_code", "velocity"]].rename(columns={"velocity": "velocity_90d"})
    out = active.merge(vel, left_on=["ship_to_location_id", "sku_code"], right_on=["store_id", "sku_code"], how="left")

    out["moq_coverage_days"] = np.where(out["velocity_90d"] > 0, out["moq_ea"] / out["velocity_90d"], np.nan)
    out["surplus_risk"] = out["moq_coverage_days"] > out["shelf_life_days"]

    cols = [
        "sku_code", "supplier_id", "ship_to_location_id", "moq_qty", "moq_uom", "eaches_per_uom",
        "moq_ea", "order_multiple", "unit_purchase_cost_per_ea", "lead_time_days", "shelf_life_days",
        "velocity_90d", "moq_coverage_days", "surplus_risk",
    ]
    return out[cols].round({"moq_coverage_days": 1})
