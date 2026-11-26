"""Demand Profiling endpoints — read-only views over the pipeline's
demand_profile / daily_panel tables. Nothing here recomputes anything;
POST /data/pipeline/run is what produces these tables.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..json_safe import df_to_records
from ..state import AppState, get_state

router = APIRouter(prefix="/demand", tags=["demand"])


def _require(state: AppState):
    try:
        state.require_loaded()
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/skus")
def list_skus(state: AppState = Depends(get_state)):
    _require(state)
    profile = state.tables["demand_profile"]
    product = state.raw.product[["sku_code", "description", "brand", "category"]]
    merged = profile[["store_id", "sku_code"]].drop_duplicates().merge(product, on="sku_code", how="left")
    return merged.to_dict(orient="records")


@router.get("/profile")
def demand_profile(
    store_id: str | None = None,
    sku_code: str | None = None,
    demand_class: str | None = None,
    category: str | None = None,
    state: AppState = Depends(get_state),
):
    _require(state)
    df = state.tables["demand_profile"]
    if category:
        df = df.merge(state.raw.product[["sku_code", "category"]], on="sku_code", how="left")
        df = df[df["category"] == category]
    if store_id:
        df = df[df["store_id"] == store_id]
    if sku_code:
        df = df[df["sku_code"] == sku_code]
    if demand_class:
        df = df[(df["demand_class_90d"] == demand_class) | (df["demand_class_365d"] == demand_class)]
    return df_to_records(df)


@router.get("/series")
def demand_series(store_id: str, sku_code: str, state: AppState = Depends(get_state)):
    _require(state)
    panel = state.tables["daily_panel"]
    g = panel[(panel["store_id"] == store_id) & (panel["sku_code"] == sku_code)].sort_values("date")
    if g.empty:
        raise HTTPException(404, f"No series found for {sku_code} at {store_id}")
    return df_to_records(g)


@router.get("/alerts")
def demand_alerts(state: AppState = Depends(get_state)):
    _require(state)
    df = state.tables["demand_profile"]
    return {
        "declining_90d": df_to_records(df[df["trend_direction_90d"] == "DECLINING"][["store_id", "sku_code"]]),
        "regime_shift": df_to_records(df[df["regime_shift_detected"] == True][["store_id", "sku_code", "demand_class_90d", "demand_class_365d"]]),  # noqa: E712
        "high_stockout_exposure": df_to_records(df[df["oos_days_90d"] >= 10][["store_id", "sku_code", "oos_days_90d"]].sort_values("oos_days_90d", ascending=False)),
        "dormant": df_to_records(df[df["demand_class_90d"] == "DORMANT"][["store_id", "sku_code"]]),
    }
