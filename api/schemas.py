"""Pydantic request models for the API. Response bodies are plain dicts
(built from the already-typed nexus_engine outputs) rather than mirrored
here — the dataframes are the source of truth for shape.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class PipelineRunRequest(BaseModel):
    data_dir: str | None = Field(None, description="Override the raw-data directory for this run (defaults to current configured dir).")
    asof: str | None = Field(None, description="Analysis as-of date, YYYY-MM-DD (defaults to current configured date).")


class ForecastRequest(BaseModel):
    store_id: str
    sku_code: str
    horizon: int = Field(30, ge=1, le=365)
    frequency: str = Field("D", pattern="^[DWM]$", description="D=daily, W=weekly, M=monthly")
    model: str | None = Field(None, description="Force a specific model key instead of auto-recommendation. See GET /forecast/models for valid keys.")
    n_folds: int = Field(3, ge=1, le=6, description="Walk-forward backtest folds used for model comparison.")


class ScenarioRequest(ForecastRequest):
    price_change_pct: float = Field(..., description="Proposed price change as a fraction, e.g. 0.05 for +5%.")
    assumed_elasticity: float | None = Field(None, description="Price elasticity of demand to assume (e.g. -1.2). If omitted, the baseline forecast is returned unchanged with a note — no effect is invented.")


class BulkForecastRequest(BaseModel):
    store_id: str | None = Field(None, description="Restrict to one store; omit for all stores.")
    horizon: int = Field(30, ge=1, le=365)
    frequency: str = Field("D", pattern="^[DWM]$")


class LLMAskRequest(BaseModel):
    question: str
    store_id: str | None = None
    sku_code: str | None = None
