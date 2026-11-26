"""Economic Profiling endpoints — read-only views over economic_profile /
supplier_profile. Gross profit (a total, not a per-unit figure) is derived
here from gm_per_ea * velocity_90d since the pipeline table stores the
per-unit figures; it's computed, not stored twice.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..json_safe import df_to_records
from ..state import AppState, get_state

router = APIRouter(prefix="/economics", tags=["economics"])


def _require(state: AppState):
    try:
        state.require_loaded()
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/profile")
def economic_profile(store_id: str | None = None, sku_code: str | None = None, has_issue: bool | None = None, state: AppState = Depends(get_state)):
    _require(state)
    df = state.tables["economic_profile"].copy()
    df["daily_gross_profit"] = (df["gm_per_ea"] * df["velocity_90d"]).round(2)
    if store_id:
        df = df[df["store_id"] == store_id]
    if sku_code:
        df = df[df["sku_code"] == sku_code]
    if has_issue is not None:
        any_issue = df["gm_issue"].notna() | df["gmroi_issue"].notna() | df["pricing_issue"].notna()
        df = df[any_issue] if has_issue else df[~any_issue]
    return df_to_records(df)


@router.get("/suppliers")
def supplier_profile(sku_code: str | None = None, surplus_risk: bool | None = None, min_coverage_days: float | None = None, state: AppState = Depends(get_state)):
    _require(state)
    df = state.tables["supplier_profile"]
    if sku_code:
        df = df[df["sku_code"] == sku_code]
    if surplus_risk is not None:
        df = df[df["surplus_risk"] == surplus_risk]
    if min_coverage_days is not None:
        df = df[df["moq_coverage_days"] >= min_coverage_days]
    return df_to_records(df)


@router.get("/alerts")
def economics_alerts(state: AppState = Depends(get_state)):
    _require(state)
    econ = state.tables["economic_profile"]
    supplier = state.tables["supplier_profile"]
    return {
        "missing_financial_data": df_to_records(econ[econ["gm_issue"].notna() | econ["gmroi_issue"].notna()][["store_id", "sku_code", "gm_issue", "gmroi_issue"]]),
        "price_history_conflicts": df_to_records(econ[econ["price_history_has_overlap"] == True][["store_id", "sku_code"]].drop_duplicates()),  # noqa: E712
        "high_moq_coverage_over_90d": df_to_records(supplier[supplier["moq_coverage_days"] > 90][["sku_code", "supplier_id", "ship_to_location_id", "moq_coverage_days"]]),
        "surplus_risk": df_to_records(supplier[supplier["surplus_risk"] == True][["sku_code", "supplier_id", "ship_to_location_id", "moq_coverage_days", "shelf_life_days"]]),  # noqa: E712
    }
