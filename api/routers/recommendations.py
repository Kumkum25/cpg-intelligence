"""SKU-to-model recommendation endpoints: the 'intelligent forecast model
selection' layer. Bulk recommendations are computed on request (not on
every pipeline run — a full sweep across every series and several
candidate models per series is too slow to run synchronously every time)
and cached in app state until the next pipeline run invalidates them.
"""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException

from nexus_engine.forecasting import recommend_for_series

from ..json_safe import df_to_records
from ..state import AppState, get_state

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.post("/compute")
def compute(horizon: int = 14, frequency: str = "D", n_folds: int = 2, state: AppState = Depends(get_state)):
    try:
        return state.compute_recommendations(horizon=horizon, frequency=frequency, n_folds=n_folds)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/status")
def status(state: AppState = Depends(get_state)):
    return {
        "computed": state.recommendations is not None,
        "stale": state.recommendations_stale,
        "computed_at": state.recommendations_computed_at.strftime("%Y-%m-%d %H:%M:%S") if state.recommendations_computed_at else None,
        "series_count": len(state.recommendations) if state.recommendations is not None else 0,
        "params": state.recommendations_params,
    }


@router.get("")
def list_recommendations(store_id: str | None = None, sku_code: str | None = None, status: str | None = None, state: AppState = Depends(get_state)):
    try:
        state.require_recommendations()
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    df = state.recommendations
    if store_id:
        df = df[df["store_id"] == store_id]
    if sku_code:
        df = df[df["sku_code"] == sku_code]
    if status:
        df = df[df["status"] == status]
    return df_to_records(df)


@router.get("/overview")
def recommendations_overview(state: AppState = Depends(get_state)):
    try:
        state.require_recommendations()
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    df = state.recommendations
    return {
        "total_series": len(df),
        "status_counts": df["status"].value_counts().to_dict(),
        "model_counts": df[df["status"] == "RECOMMENDED"]["recommended_model_name"].value_counts().to_dict(),
        "confidence_counts": df["confidence"].value_counts().to_dict(),
        "insufficient_data_series": df_to_records(df[df["status"] == "INSUFFICIENT_DATA"][["store_id", "sku_code", "reason"]]),
    }


@router.get("/{store_id}/{sku_code}")
def recommendation_detail(store_id: str, sku_code: str, horizon: int = 30, frequency: str = "D", n_folds: int = 3, state: AppState = Depends(get_state)):
    try:
        state.require_loaded()
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    try:
        rec = recommend_for_series(state.tables["daily_panel"], state.tables["demand_profile"], store_id, sku_code, horizon=horizon, frequency=frequency, n_folds=n_folds)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return asdict(rec)
