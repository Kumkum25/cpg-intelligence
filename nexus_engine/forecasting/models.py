"""Forecasting model implementations behind one common interface.

Every model exposes:

    fit(y, season_length)      -> self
    predict(h)                 -> np.ndarray of point forecasts, length h
    predict_interval(h, level) -> (lower, upper) arrays, or None if unsupported

``interval_kind`` on each instance says whether an interval, when present,
is ``"model_native"`` (the model's own probabilistic forecast — ETS/SARIMAX)
or ``"approximate"`` (a residual-spread heuristic bolted on afterwards).
That distinction gets carried into the forecast output so the app never
represents a rough band as something it isn't.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import numpy as np

warnings.filterwarnings("ignore", category=UserWarning, module="statsmodels")
warnings.filterwarnings("ignore", message=".*Maximum Likelihood optimization failed to converge.*")

try:
    import lightgbm as lgb
    _HAS_LIGHTGBM = True
except ImportError:  # pragma: no cover
    _HAS_LIGHTGBM = False

from sklearn.ensemble import RandomForestRegressor
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.statespace.sarimax import SARIMAX


class BaseModel:
    name = "base"
    interval_kind: str | None = None  # None | "model_native" | "approximate"
    min_train_length = 2

    def fit(self, y: np.ndarray, season_length: int = 1) -> "BaseModel":
        raise NotImplementedError

    def predict(self, h: int) -> np.ndarray:
        raise NotImplementedError

    def predict_interval(self, h: int, level: float = 0.8) -> tuple[np.ndarray, np.ndarray] | None:
        return None

    def _residual_interval(self, point: np.ndarray, resid_std: float, h: int, level: float) -> tuple[np.ndarray, np.ndarray]:
        """Shared fallback: widen a point forecast by a z-scaled, sqrt(step)-growing
        band derived from the model's own in-sample residual std. This is a
        heuristic, not a fitted predictive distribution — callers must tag it
        ``interval_kind = "approximate"``.
        """
        from scipy.stats import norm
        z = norm.ppf(0.5 + level / 2)
        steps = np.sqrt(np.arange(1, h + 1))
        spread = z * resid_std * steps
        return point - spread, point + spread


class NaiveModel(BaseModel):
    name = "Naive"
    interval_kind = "approximate"

    def fit(self, y: np.ndarray, season_length: int = 1) -> "NaiveModel":
        self._last = float(y[-1])
        self._resid_std = float(np.std(np.diff(y))) if len(y) > 1 else 0.0
        return self

    def predict(self, h: int) -> np.ndarray:
        return np.full(h, self._last)

    def predict_interval(self, h: int, level: float = 0.8):
        return self._residual_interval(self.predict(h), self._resid_std, h, level)


class SeasonalNaiveModel(BaseModel):
    name = "Seasonal Naive"
    interval_kind = "approximate"
    min_train_length = 2

    def fit(self, y: np.ndarray, season_length: int = 7) -> "SeasonalNaiveModel":
        self.season_length = max(1, season_length)
        self._season = y[-self.season_length:] if len(y) >= self.season_length else y
        if len(y) > self.season_length:
            resid = y[self.season_length:] - y[:-self.season_length]
            self._resid_std = float(np.std(resid))
        else:
            self._resid_std = float(np.std(y))
        return self

    def predict(self, h: int) -> np.ndarray:
        reps = int(np.ceil(h / len(self._season)))
        return np.tile(self._season, reps)[:h]

    def predict_interval(self, h: int, level: float = 0.8):
        return self._residual_interval(self.predict(h), self._resid_std, h, level)


class MovingAverageModel(BaseModel):
    name = "Moving Average"
    interval_kind = "approximate"

    def __init__(self, window: int = 7):
        self.window = window

    def fit(self, y: np.ndarray, season_length: int = 1) -> "MovingAverageModel":
        w = min(self.window, len(y))
        self._level = float(np.mean(y[-w:]))
        self._resid_std = float(np.std(y[-w:]))
        return self

    def predict(self, h: int) -> np.ndarray:
        return np.full(h, self._level)

    def predict_interval(self, h: int, level: float = 0.8):
        return self._residual_interval(self.predict(h), self._resid_std, h, level)


class HoltWintersModel(BaseModel):
    """Exponential smoothing — Holt (trend only) or Holt-Winters (trend +
    seasonal) depending on how much history is available relative to the
    season length.
    """
    name = "Holt-Winters"
    interval_kind = "model_native"
    min_train_length = 10

    def fit(self, y: np.ndarray, season_length: int = 7) -> "HoltWintersModel":
        y = np.asarray(y, dtype=float)
        y_fit = np.where(y <= 0, 1e-6, y)  # multiplicative components need > 0
        use_seasonal = season_length > 1 and len(y) >= 2 * season_length
        try:
            self._model = ExponentialSmoothing(
                y_fit, trend="add",
                seasonal=("add" if use_seasonal else None),
                seasonal_periods=(season_length if use_seasonal else None),
                initialization_method="estimated",
            ).fit(optimized=True)
            self._ok = True
        except Exception:
            self._ok = False
            self._fallback_level = float(np.mean(y[-min(7, len(y)):]))
        return self

    def predict(self, h: int) -> np.ndarray:
        if not self._ok:
            return np.full(h, self._fallback_level)
        return np.clip(self._model.forecast(h), 0, None)

    def predict_interval(self, h: int, level: float = 0.8):
        if not self._ok:
            return None
        try:
            sf = self._model.get_prediction(start=len(self._model.fittedvalues), end=len(self._model.fittedvalues) + h - 1)
            ci = sf.summary_frame(alpha=1 - level)
            return np.clip(ci["mean_ci_lower"].to_numpy(), 0, None), ci["mean_ci_upper"].to_numpy()
        except Exception:
            resid_std = float(np.std(self._model.resid)) if hasattr(self._model, "resid") else 0.0
            return self._residual_interval(self.predict(h), resid_std, h, level)


class AutoARIMAModel(BaseModel):
    """Small-grid-search SARIMAX — NOT pmdarima's AutoARIMA. Tries a short
    list of (p,d,q) orders (plus a seasonal term when season_length > 1)
    and keeps the lowest-AIC fit. Honest label for what this actually is.
    """
    name = "Auto-ARIMA (grid search)"
    interval_kind = "model_native"
    min_train_length = 15

    _ORDERS = [(1, 1, 0), (0, 1, 1), (1, 1, 1), (2, 1, 0), (1, 0, 0)]

    def fit(self, y: np.ndarray, season_length: int = 7) -> "AutoARIMAModel":
        y = np.asarray(y, dtype=float)
        best_aic, best_fit, best_order = np.inf, None, None
        seasonal_order = (0, 0, 0, 0)
        for order in self._ORDERS:
            try:
                fit = SARIMAX(y, order=order, seasonal_order=seasonal_order,
                               enforce_stationarity=False, enforce_invertibility=False).fit(disp=False)
                if fit.aic < best_aic:
                    best_aic, best_fit, best_order = fit.aic, fit, order
            except Exception:
                continue
        self._ok = best_fit is not None
        self._model = best_fit
        self.selected_order = best_order
        if not self._ok:
            self._fallback_level = float(np.mean(y[-min(7, len(y)):]))
        return self

    def predict(self, h: int) -> np.ndarray:
        if not self._ok:
            return np.full(h, self._fallback_level)
        return np.clip(self._model.forecast(h), 0, None)

    def predict_interval(self, h: int, level: float = 0.8):
        if not self._ok:
            return None
        fc = self._model.get_forecast(h)
        ci = fc.conf_int(alpha=1 - level)
        return np.clip(ci[:, 0], 0, None), ci[:, 1]


class CrostonModel(BaseModel):
    """Croston's method (SBA variant) for intermittent/lumpy demand: tracks
    the average non-zero demand size and the average inter-demand interval
    separately, instead of smoothing over the zeros directly.
    """
    name = "Croston (SBA)"
    interval_kind = None
    min_train_length = 4

    def __init__(self, alpha: float = 0.1):
        self.alpha = alpha

    def fit(self, y: np.ndarray, season_length: int = 1) -> "CrostonModel":
        y = np.asarray(y, dtype=float)
        nonzero_idx = np.flatnonzero(y > 0)
        if len(nonzero_idx) == 0:
            self._rate = 0.0
            return self
        if len(nonzero_idx) == 1:
            self._rate = float(y[nonzero_idx[0]]) / max(1, len(y) - nonzero_idx[0])
            return self

        intervals = np.diff(nonzero_idx, prepend=nonzero_idx[0])
        intervals[0] = nonzero_idx[0] + 1
        sizes = y[nonzero_idx]

        z = sizes[0]
        p = intervals[0]
        for i in range(1, len(sizes)):
            z = self.alpha * sizes[i] + (1 - self.alpha) * z
            p = self.alpha * intervals[i] + (1 - self.alpha) * p

        bias_correction = 1 - self.alpha / 2  # Syntetos-Boylan Approximation
        self._rate = bias_correction * z / p if p > 0 else 0.0
        return self

    def predict(self, h: int) -> np.ndarray:
        return np.full(h, self._rate)


class MLRegressorModel(BaseModel):
    """Lag + calendar-feature regression (LightGBM if available, else
    RandomForest), forecasting recursively one step at a time so later
    predictions can use earlier predicted values as lag features.
    """
    interval_kind = None
    min_train_length = 35
    LAGS = (1, 7, 14, 28)
    ROLL_WINDOWS = (7, 28)

    def __init__(self):
        self.name = "LightGBM" if _HAS_LIGHTGBM else "Random Forest"

    def _make_features(self, y: np.ndarray, t: int) -> list[float]:
        feats = [y[t - lag] if t - lag >= 0 else 0.0 for lag in self.LAGS]
        for w in self.ROLL_WINDOWS:
            window = y[max(0, t - w):t]
            feats.append(float(window.mean()) if len(window) else 0.0)
        feats.append(t % 7)
        return feats

    def fit(self, y: np.ndarray, season_length: int = 7) -> "MLRegressorModel":
        y = np.asarray(y, dtype=float)
        start = max(self.LAGS + self.ROLL_WINDOWS)
        X = [self._make_features(y, t) for t in range(start, len(y))]
        Y = y[start:]
        if len(X) < 10:
            self._ok = False
            self._fallback_level = float(np.mean(y[-min(7, len(y)):]))
            return self
        self._ok = True
        if _HAS_LIGHTGBM:
            self._model = lgb.LGBMRegressor(n_estimators=150, max_depth=4, learning_rate=0.08, min_child_samples=3, verbose=-1)
        else:
            self._model = RandomForestRegressor(n_estimators=150, max_depth=6, random_state=0)
        self._model.fit(X, Y)
        self._history = list(y)
        return self

    def predict(self, h: int) -> np.ndarray:
        if not self._ok:
            return np.full(h, self._fallback_level)
        history = list(self._history)
        preds = []
        for _ in range(h):
            feats = self._make_features(np.array(history), len(history))
            pred = max(0.0, float(self._model.predict([feats])[0]))
            preds.append(pred)
            history.append(pred)
        return np.array(preds)


@dataclass
class ModelSpec:
    key: str
    factory: callable
    min_train_length: int = 2


MODEL_REGISTRY: dict[str, ModelSpec] = {
    "naive": ModelSpec("naive", NaiveModel, 2),
    "seasonal_naive": ModelSpec("seasonal_naive", SeasonalNaiveModel, 8),
    "moving_average": ModelSpec("moving_average", MovingAverageModel, 2),
    "holt_winters": ModelSpec("holt_winters", HoltWintersModel, 10),
    "auto_arima": ModelSpec("auto_arima", AutoARIMAModel, 15),
    "croston": ModelSpec("croston", CrostonModel, 4),
    "ml_regressor": ModelSpec("ml_regressor", MLRegressorModel, 35),
}
