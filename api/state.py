"""Process-wide application state: the currently loaded dataset, the
as-of date, and the computed pipeline tables. One instance, created at
import time, shared by every router via `get_state()`.

This is intentionally a plain in-memory object rather than a database —
the whole point of this app is a small analyst tool over a CSV-sized
dataset, not a multi-tenant persistence layer. Restarting the process
means re-running the pipeline (cheap: a few seconds for this data size).
"""
from __future__ import annotations

import logging

import pandas as pd

from nexus_engine import pipeline as pipeline_mod
from nexus_engine.forecasting import recommend_bulk, run_forecast
from nexus_engine.ingest import RawData, load_all

from . import config

logger = logging.getLogger("nexus.state")

# Bulk recommendation sweeps every series x several candidate models x
# backtest folds, so it's deliberately cheaper than an on-demand single-SKU
# forecast (shorter horizon, fewer folds) and computed on request rather
# than blocking every pipeline run.
BULK_REC_HORIZON = 14
BULK_REC_FREQUENCY = "D"
BULK_REC_N_FOLDS = 2


class AppState:
    def __init__(self):
        self.data_dir: str = config.DEFAULT_DATA_DIR
        self.asof: pd.Timestamp = config.DEFAULT_ASOF
        self.raw: RawData | None = None
        self.tables: dict[str, pd.DataFrame] = {}
        self.loaded: bool = False
        self.last_error: str | None = None
        self.recommendations: pd.DataFrame | None = None
        self.recommendations_computed_at: pd.Timestamp | None = None
        self.recommendations_stale: bool = True
        self.recommendations_params: dict | None = None
        self.bulk_forecast: pd.DataFrame | None = None
        self.bulk_forecast_computed_at: pd.Timestamp | None = None

    def run_pipeline(self, data_dir: str | None = None, asof: str | pd.Timestamp | None = None) -> dict:
        if data_dir:
            self.data_dir = data_dir
        if asof:
            self.asof = pd.Timestamp(asof)

        logger.info("Running pipeline: data_dir=%s asof=%s", self.data_dir, self.asof.date())
        try:
            self.raw = load_all(self.data_dir)
            self.tables = pipeline_mod.run(self.data_dir, config.OUTPUT_DIR, self.asof)
            self.loaded = True
            self.last_error = None
        except Exception as exc:
            self.loaded = False
            self.last_error = str(exc)
            logger.exception("Pipeline run failed")
            raise
        finally:
            # A new dataset/as-of date invalidates any previously computed
            # recommendations — never let stale SKU-to-model mappings from a
            # prior upload linger silently.
            self.recommendations = None
            self.recommendations_computed_at = None
            self.recommendations_stale = True
            self.recommendations_params = None
            self.bulk_forecast = None
            self.bulk_forecast_computed_at = None

        return {
            "data_dir": self.data_dir,
            "asof": self.asof.strftime("%Y-%m-%d"),
            "row_counts": {name: len(df) for name, df in self.tables.items()},
        }

    def compute_recommendations(self, horizon: int = BULK_REC_HORIZON, frequency: str = BULK_REC_FREQUENCY, n_folds: int = BULK_REC_N_FOLDS) -> dict:
        self.require_loaded()
        logger.info("Computing model recommendations for %d series...", len(self.tables["demand_profile"][["store_id", "sku_code"]].drop_duplicates()))
        self.recommendations = recommend_bulk(self.tables["daily_panel"], self.tables["demand_profile"], horizon=horizon, frequency=frequency, n_folds=n_folds)
        self.recommendations_computed_at = pd.Timestamp.now()
        self.recommendations_stale = False
        self.recommendations_params = {"horizon": horizon, "frequency": frequency, "n_folds": n_folds}
        return {
            "series_count": len(self.recommendations),
            "status_counts": self.recommendations["status"].value_counts().to_dict(),
            "computed_at": self.recommendations_computed_at.strftime("%Y-%m-%d %H:%M:%S"),
        }

    def compute_bulk_forecast(self, store_id: str | None = None, horizon: int = 30, frequency: str = "D") -> dict:
        """Generates a forecast for every RECOMMENDED series (using its own
        recommended model), long-format: one row per store/sku/date. Series
        with INSUFFICIENT_DATA or NOT_RANGED status are skipped, not forced
        through a misleading forecast — the caller can see why in /recommendations.
        """
        self.require_recommendations()
        eligible = self.recommendations[self.recommendations["status"] == "RECOMMENDED"]
        if store_id:
            eligible = eligible[eligible["store_id"] == store_id]

        rows, skipped = [], []
        for r in eligible.itertuples(index=False):
            try:
                fc = run_forecast(self.tables["daily_panel"], self.tables["demand_profile"], r.store_id, r.sku_code,
                                   horizon=horizon, frequency=frequency, model_override=r.recommended_model)
            except ValueError as exc:
                skipped.append({"store_id": r.store_id, "sku_code": r.sku_code, "reason": str(exc)})
                continue
            for d, v in zip(fc.forecast_dates, fc.forecast_values):
                rows.append({"store_id": r.store_id, "sku_code": r.sku_code, "model": fc.selected_model,
                             "demand_class": fc.demand_class, "date": d, "forecast_value": v, "trend": fc.trend})

        self.bulk_forecast = pd.DataFrame(rows)
        self.bulk_forecast_computed_at = pd.Timestamp.now()
        return {
            "series_forecasted": int(len(eligible)) - len(skipped),
            "series_skipped": skipped,
            "total_rows": len(self.bulk_forecast),
            "horizon": horizon, "frequency": frequency,
            "computed_at": self.bulk_forecast_computed_at.strftime("%Y-%m-%d %H:%M:%S"),
        }

    def require_loaded(self):
        if not self.loaded:
            raise RuntimeError("Pipeline has not been run yet. Call POST /data/pipeline/run first.")

    def require_recommendations(self):
        self.require_loaded()
        if self.recommendations is None:
            raise RuntimeError("Model recommendations have not been computed yet. Call POST /recommendations/compute first.")


_state = AppState()


def get_state() -> AppState:
    return _state
