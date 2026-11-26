"""Orchestrates ingest -> clean -> calendar -> classify -> economics into the
final demand and economic profile tables, and writes them to an output dir.
"""
from __future__ import annotations

import os

import pandas as pd

from . import calendar as cal_mod
from . import classify
from . import clean
from . import economics
from . import interpretation
from .ingest import RawData, load_all

DEFAULT_ASOF = pd.Timestamp("2026-11-20")


def run(data_dir: str, out_dir: str, asof: pd.Timestamp = DEFAULT_ASOF) -> dict[str, pd.DataFrame]:
    os.makedirs(out_dir, exist_ok=True)

    raw: RawData = load_all(data_dir)

    daily_demand = clean.build_daily_demand(raw)
    daily_returns = clean.build_daily_returns(raw)
    panel = cal_mod.build_daily_panel(raw, daily_demand, asof)

    profile_90d = classify.profile_window(panel, asof, 90)
    profile_365d = classify.profile_window(panel, asof, 365)
    seasonality = classify.seasonality_profile(panel)
    regime = classify.regime_shift_flags(profile_90d, profile_365d)

    demand_profile = (
        profile_90d.merge(profile_365d, on=["store_id", "sku_code"], suffixes=("_90d", "_365d"))
        .merge(seasonality, on=["store_id", "sku_code"], how="left")
        .merge(regime[["store_id", "sku_code", "regime_shift_detected"]], on=["store_id", "sku_code"], how="left")
    )

    # Zero-sales frequency, new/discontinued flags, and a plain-language
    # interpretation — additive columns, computed from data already on hand
    # (never hardcoded to a particular SKU/store count or roster).
    demand_profile["zero_sales_frequency_90d"] = demand_profile.apply(
        lambda r: interpretation.zero_sales_frequency(r["N_90d"], r["K_90d"]), axis=1)
    demand_profile["zero_sales_frequency_365d"] = demand_profile.apply(
        lambda r: interpretation.zero_sales_frequency(r["N_365d"], r["K_365d"]), axis=1)

    product_dates = raw.product[["sku_code", "launch_date", "delist_date"]]
    demand_profile = demand_profile.merge(product_dates, on="sku_code", how="left")
    status_flags = demand_profile.apply(
        lambda r: interpretation.product_status_flags(r["launch_date"], r["delist_date"], asof), axis=1, result_type="expand")
    demand_profile[["is_new_product", "is_discontinued"]] = status_flags
    demand_profile = demand_profile.drop(columns=["launch_date", "delist_date"])

    demand_profile["business_interpretation_90d"] = demand_profile.apply(
        lambda r: interpretation.business_interpretation(r.to_dict()), axis=1)

    econ = economics.economics_summary(raw, profile_90d, asof)
    econ_gmroi = economics.gmroi_summary(raw, econ, asof)
    supplier = economics.supplier_summary(raw, profile_90d, asof)

    tables = {
        "daily_demand": daily_demand,
        "daily_returns": daily_returns,
        "daily_panel": panel,
        "demand_profile": demand_profile,
        "economic_profile": econ_gmroi,
        "supplier_profile": supplier,
    }
    for name, df in tables.items():
        df.to_csv(os.path.join(out_dir, f"{name}.csv"), index=False)

    return tables
