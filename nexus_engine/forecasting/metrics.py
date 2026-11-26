"""Forecast accuracy metrics, written to behave sanely on intermittent and
zero-heavy demand series (the common case in this dataset) rather than
blowing up or silently returning misleading numbers.
"""
from __future__ import annotations

import numpy as np


def mae(actual: np.ndarray, forecast: np.ndarray) -> float:
    return float(np.mean(np.abs(actual - forecast)))


def rmse(actual: np.ndarray, forecast: np.ndarray) -> float:
    return float(np.sqrt(np.mean((actual - forecast) ** 2)))


def bias(actual: np.ndarray, forecast: np.ndarray) -> float:
    """Mean signed error. Positive = over-forecasting, negative = under-forecasting."""
    return float(np.mean(forecast - actual))


def wape(actual: np.ndarray, forecast: np.ndarray) -> float:
    """Weighted Absolute Percentage Error = sum|e| / sum|actual|.

    Unlike MAPE, a single zero-demand day doesn't blow this up — it's only
    undefined when the *entire* window summed to zero actual demand.
    """
    denom = np.sum(np.abs(actual))
    if denom == 0:
        return float("nan")
    return float(np.sum(np.abs(actual - forecast)) / denom)


def mase(actual: np.ndarray, forecast: np.ndarray, train: np.ndarray, season_length: int = 1) -> float:
    """Mean Absolute Scaled Error: MAE of the forecast divided by the MAE of
    a naive (or seasonal-naive) one-step benchmark computed on the
    *training* series. Scale-free and well-behaved on intermittent demand,
    as long as the training series isn't itself all-zero or constant.
    """
    if len(train) <= season_length:
        return float("nan")
    naive_errors = np.abs(train[season_length:] - train[:-season_length])
    scale = np.mean(naive_errors)
    if scale == 0 or not np.isfinite(scale):
        return float("nan")
    return float(mae(actual, forecast) / scale)


def all_metrics(actual: np.ndarray, forecast: np.ndarray, train: np.ndarray, season_length: int = 1) -> dict:
    return {
        "mae": round(mae(actual, forecast), 4),
        "rmse": round(rmse(actual, forecast), 4),
        "wape": (round(wape(actual, forecast), 4) if np.isfinite(wape(actual, forecast)) else None),
        "mase": (round(mase(actual, forecast, train, season_length), 4) if np.isfinite(mase(actual, forecast, train, season_length)) else None),
        "bias": round(bias(actual, forecast), 4),
    }
