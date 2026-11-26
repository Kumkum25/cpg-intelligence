"""Maps a demand classification to the candidate models worth trying.

The point is explicitly to *not* force every model onto every SKU:
Croston makes no sense on a smooth fast-mover, and ARIMA is wasted compute
on a SKU that sells on 1 day in 20.
"""
from __future__ import annotations

from .models import MODEL_REGISTRY

CANDIDATES_BY_CLASS: dict[str, list[str]] = {
    "SMOOTH": ["naive", "seasonal_naive", "moving_average", "holt_winters", "auto_arima", "ml_regressor"],
    "ERRATIC": ["seasonal_naive", "moving_average", "holt_winters", "ml_regressor", "croston"],
    "INTERMITTENT": ["croston", "naive", "ml_regressor"],
    "LUMPY": ["croston", "ml_regressor", "naive"],
    "DORMANT": ["naive"],
    "INSUFFICIENT": ["naive", "moving_average"],
}

DEFAULT_CANDIDATES = ["naive", "seasonal_naive", "moving_average"]


def candidate_models(demand_class: str) -> list[str]:
    return CANDIDATES_BY_CLASS.get(demand_class, DEFAULT_CANDIDATES)


def shortlist_models(demand_class: str, available_n: int) -> list[str]:
    """Data-sufficiency-aware shortlist: start from the demand-class
    candidate pool, then drop anything that mathematically can't be fit
    with the history actually available (no point backtesting, or
    recommending, Auto-ARIMA on a SKU with 10 days of life). Always keeps
    at least Naive as a floor, as long as there are enough points for it.
    """
    base = candidate_models(demand_class)
    filtered = [m for m in base if MODEL_REGISTRY[m].min_train_length <= available_n]
    if not filtered and available_n >= MODEL_REGISTRY["naive"].min_train_length:
        filtered = ["naive"]
    return filtered
