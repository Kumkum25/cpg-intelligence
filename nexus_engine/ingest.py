"""Load the raw Nexus CPG sample-data CSVs with sane dtypes.

Nothing in here applies business logic — it only parses dates/bools so every
downstream module works with typed columns instead of re-parsing strings.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import pandas as pd

BOOL_MAP = {"True": True, "False": False, True: True, False: False, "": pd.NA}


def _read(path: str, date_cols: list[str] | None = None, bool_cols: list[str] | None = None) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
    for c in date_cols or []:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    for c in bool_cols or []:
        if c in df.columns:
            df[c] = df[c].map(BOOL_MAP)
    return df


@dataclass
class RawData:
    pos: pd.DataFrame
    product: pd.DataFrame
    location: pd.DataFrame
    ranging: pd.DataFrame
    calendar: pd.DataFrame
    inventory_daily: pd.DataFrame
    sku_economics: pd.DataFrame
    supplier_constraints: pd.DataFrame
    inventory_valuation_weekly: pd.DataFrame


def load_all(data_dir: str) -> RawData:
    p = lambda name: os.path.join(data_dir, name)

    pos = _read(p("pos_sales_transactions.csv"), date_cols=["txn_datetime"])
    for num_col in ("qty", "unit_price", "line_amount"):
        pos[num_col] = pd.to_numeric(pos[num_col], errors="coerce")

    product = _read(p("product_master.csv"), date_cols=["launch_date", "delist_date"])
    product["eaches_per_case"] = pd.to_numeric(product["eaches_per_case"], errors="coerce")

    location = _read(p("location_master.csv"), date_cols=["open_date"])

    ranging = _read(p("ranging.csv"), date_cols=["ranged_from", "ranged_to"])

    calendar = _read(
        p("store_calendar_feed_log.csv"),
        date_cols=["date"],
        bool_cols=["store_open", "pos_feed_received", "feed_complete"],
    )

    inventory_daily = _read(p("inventory_daily.csv"), date_cols=["inventory_date"], bool_cols=["oos_eod_flag"])
    inventory_daily["on_hand_eod_ea"] = pd.to_numeric(inventory_daily["on_hand_eod_ea"], errors="coerce")

    sku_economics = _read(p("sku_economics.csv"), date_cols=["effective_from", "effective_to"])
    for c in ("net_price_per_ea", "cogs_per_ea"):
        sku_economics[c] = pd.to_numeric(sku_economics[c], errors="coerce")

    supplier_constraints = _read(p("supplier_constraints.csv"), date_cols=["effective_from", "effective_to"])
    for c in ("moq_qty", "eaches_per_uom", "order_multiple", "unit_purchase_cost_per_ea", "lead_time_days", "shelf_life_days"):
        supplier_constraints[c] = pd.to_numeric(supplier_constraints[c], errors="coerce")

    inv_val = _read(p("inventory_valuation_weekly.csv"), date_cols=["inventory_date"])
    for c in ("on_hand_ea", "inventory_value_at_cost"):
        inv_val[c] = pd.to_numeric(inv_val[c], errors="coerce")

    return RawData(
        pos=pos,
        product=product,
        location=location,
        ranging=ranging,
        calendar=calendar,
        inventory_daily=inventory_daily,
        sku_economics=sku_economics,
        supplier_constraints=supplier_constraints,
        inventory_valuation_weekly=inv_val,
    )
