"""Aggregate KPIs for the Overview dashboard page — everything here is a
straightforward aggregation over already-computed pipeline tables, no new
calculations.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..json_safe import safe_float
from ..state import AppState, get_state

router = APIRouter(prefix="/overview", tags=["overview"])


@router.get("")
def overview(state: AppState = Depends(get_state)):
    if not state.loaded:
        raise HTTPException(409, "Pipeline has not been run yet. Call POST /data/pipeline/run first.")

    demand = state.tables["demand_profile"]
    econ = state.tables["economic_profile"]
    supplier = state.tables["supplier_profile"]
    daily = state.tables["daily_demand"]

    class_counts = demand["demand_class_90d"].value_counts().to_dict()
    econ_valid = econ[econ["gm_per_ea"].notna()]
    total_gross_profit_daily = float((econ_valid["gm_per_ea"] * econ_valid["velocity_90d"]).sum())

    return {
        "asof": state.asof.strftime("%Y-%m-%d"),
        "total_skus": int(state.raw.product["sku_code"].nunique()),
        "total_stores": int(state.raw.location["store_id"].nunique()),
        "total_series": int(len(demand)),
        "total_units_sold_lifetime": float(daily["sold_ea"].sum()),
        "avg_daily_demand_velocity": safe_float(round(demand["velocity_90d"].replace(0, None).mean(), 3)),
        "total_estimated_daily_gross_profit": round(total_gross_profit_daily, 2),
        "demand_class_counts_90d": class_counts,
        "declining_sku_count": int((demand["trend_direction_90d"] == "DECLINING").sum()),
        "regime_shift_count": int((demand["regime_shift_detected"] == True).sum()),  # noqa: E712
        "high_moq_risk_count": int((supplier["moq_coverage_days"] > 90).sum()),
        "surplus_risk_count": int((supplier["surplus_risk"] == True).sum()),  # noqa: E712
        "stockout_exposed_count": int((demand["oos_days_90d"] >= 10).sum()),
        "missing_financial_data_count": int((econ["gm_issue"].notna() | econ["gmroi_issue"].notna()).sum()),
    }
