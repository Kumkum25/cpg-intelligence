"""Forecasting endpoints: model catalog, business-factor availability,
forecast generation, and price-change scenario analysis.
"""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException

from nexus_engine.forecasting import run_forecast
from nexus_engine.forecasting.features import factor_availability, price_change_history, simulate_price_change
from nexus_engine.forecasting.models import MODEL_REGISTRY
from nexus_engine.forecasting.selector import candidate_models

from ..json_safe import df_to_records
from ..schemas import BulkForecastRequest, ForecastRequest, ScenarioRequest
from ..state import AppState, get_state

router = APIRouter(prefix="/forecast", tags=["forecast"])


def _require(state: AppState):
    try:
        state.require_loaded()
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/models")
def list_models():
    return {key: spec.factory().name for key, spec in MODEL_REGISTRY.items()}


@router.get("/candidates")
def candidates_for(demand_class: str):
    return {"demand_class": demand_class, "candidate_models": candidate_models(demand_class)}


@router.get("/business-factors")
def business_factors(state: AppState = Depends(get_state)):
    _require(state)
    return [vars(f) for f in factor_availability(state.raw)]


@router.get("/business-factors/price-history")
def price_history(store_id: str, sku_code: str, state: AppState = Depends(get_state)):
    _require(state)
    df = price_change_history(state.raw, store_id, sku_code)
    return df_to_records(df)


@router.post("/run")
def forecast_run(req: ForecastRequest, state: AppState = Depends(get_state)):
    _require(state)
    try:
        result = run_forecast(
            state.tables["daily_panel"], state.tables["demand_profile"],
            req.store_id, req.sku_code, horizon=req.horizon, frequency=req.frequency,
            model_override=req.model, n_folds=req.n_folds,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return asdict(result)


@router.post("/bulk")
def forecast_bulk(req: BulkForecastRequest, state: AppState = Depends(get_state)):
    try:
        summary = state.compute_bulk_forecast(store_id=req.store_id, horizon=req.horizon, frequency=req.frequency)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    return summary


@router.get("/bulk/results")
def forecast_bulk_results(store_id: str | None = None, sku_code: str | None = None, state: AppState = Depends(get_state)):
    if state.bulk_forecast is None:
        raise HTTPException(409, "No bulk forecast computed yet. Call POST /forecast/bulk first.")
    df = state.bulk_forecast
    if store_id:
        df = df[df["store_id"] == store_id]
    if sku_code:
        df = df[df["sku_code"] == sku_code]
    return df_to_records(df)


@router.post("/scenario")
def forecast_scenario(req: ScenarioRequest, state: AppState = Depends(get_state)):
    _require(state)
    try:
        baseline = run_forecast(
            state.tables["daily_panel"], state.tables["demand_profile"],
            req.store_id, req.sku_code, horizon=req.horizon, frequency=req.frequency,
            model_override=req.model, n_folds=req.n_folds,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    import numpy as np
    scenario = simulate_price_change(np.array(baseline.forecast_values), req.price_change_pct, req.assumed_elasticity)
    return {"baseline": asdict(baseline), "scenario": scenario}
