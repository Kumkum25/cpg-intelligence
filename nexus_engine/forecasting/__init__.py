"""Forecasting engine: models, backtesting, model selection, and the
run_forecast() orchestrator. See forecast.py for the single entry point,
and recommend.py for the explainable model-recommendation layer built on
top of it.
"""
from .forecast import ForecastResult, run_forecast
from .recommend import ModelRecommendation, recommend_bulk, recommend_for_series
from .selector import candidate_models, shortlist_models

__all__ = [
    "run_forecast", "ForecastResult",
    "candidate_models", "shortlist_models",
    "recommend_for_series", "recommend_bulk", "ModelRecommendation",
]
