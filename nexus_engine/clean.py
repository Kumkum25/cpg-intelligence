"""POS cleaning and daily aggregation — traps #1-#5 from the README.

    1. Exact duplicate lines (``-RESEND`` ingest batches)   -> dedupe on (transaction_id, line_no)
    2. Voided lines                                          -> excluded entirely
    3. Returns                                                -> excluded from gross demand, tracked separately
    4. Mixed UOM (CS vs EA)                                   -> converted to EA before aggregating
    5. Multiple lines per SKU per day                         -> summed to one row per store/sku/date
"""
from __future__ import annotations

import pandas as pd

from .ingest import RawData


def dedupe_lines(pos: pd.DataFrame) -> pd.DataFrame:
    """Trap #1: a ``-RESEND`` ingest batch re-sends the exact same line.

    Dedup key is the natural key of a line: (transaction_id, line_no). We keep
    the first occurrence — the resend is a verbatim repeat, not a correction,
    so there is nothing to merge. A different line_no with the same SKU/qty on
    the same transaction is a *distinct* line (e.g. a second scan) and must be
    kept.
    """
    before = len(pos)
    deduped = pos.drop_duplicates(subset=["transaction_id", "line_no"], keep="first")
    return deduped.assign(_dupes_removed=before - len(deduped))


def to_eaches(df: pd.DataFrame, product: pd.DataFrame) -> pd.DataFrame:
    """Trap #4: convert CS quantities to EA using the SKU's case pack before
    any aggregation happens. EA rows pass through unchanged.
    """
    out = df.merge(product[["sku_code", "eaches_per_case"]], on="sku_code", how="left", validate="many_to_one")
    is_cs = out["uom"] == "CS"
    out["qty_ea"] = out["qty"]
    out.loc[is_cs, "qty_ea"] = out.loc[is_cs, "qty"] * out.loc[is_cs, "eaches_per_case"]
    return out.drop(columns=["eaches_per_case"])


def build_daily_demand(raw: RawData) -> pd.DataFrame:
    """Gross demand: COMPLETED SALE lines only, deduped, CS->EA, summed per
    store/sku/day. Trap #2 (VOIDED) and trap #3 (RETURN) are both excluded
    here — returns get their own series via :func:`build_daily_returns`.
    """
    pos = dedupe_lines(raw.pos)
    sales = pos[(pos["line_status"] == "COMPLETED") & (pos["txn_type"] == "SALE")].copy()
    sales = to_eaches(sales, raw.product)
    sales["date"] = sales["txn_datetime"].dt.date.astype("datetime64[ns]")

    daily = (
        sales.groupby(["store_id", "sku_code", "date"], as_index=False)
        .agg(sold_ea=("qty_ea", "sum"), line_count=("qty_ea", "size"))
    )
    return daily


def build_daily_returns(raw: RawData) -> pd.DataFrame:
    """Trap #3: returns (``txn_type == RETURN``, negative qty) summed per
    store/sku/day, kept as a separate, positive-magnitude series rather than
    netted against gross demand. Disposition policy (net vs. gross reporting)
    is intentionally left to downstream consumers — this just exposes the
    volume.
    """
    pos = dedupe_lines(raw.pos)
    returns = pos[(pos["line_status"] == "COMPLETED") & (pos["txn_type"] == "RETURN")].copy()
    returns = to_eaches(returns, raw.product)
    returns["date"] = returns["txn_datetime"].dt.date.astype("datetime64[ns]")
    returns["returned_ea"] = returns["qty_ea"].abs()

    daily = (
        returns.groupby(["store_id", "sku_code", "date"], as_index=False)
        .agg(returned_ea=("returned_ea", "sum"))
    )
    return daily
