"""Nexus CPG Intelligence API.

Run with:  uvicorn api.main:app --reload --port 8000
Docs at:   http://localhost:8000/docs
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import data, demand, economics, forecasting, health, llm, overview, recommendations, reports
from .state import get_state

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("nexus.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    state = get_state()
    try:
        state.run_pipeline()
        logger.info("Startup pipeline run OK: %s", {k: len(v) for k, v in state.tables.items()})
    except Exception:
        logger.exception("Startup pipeline run failed — call POST /data/pipeline/run manually once data is in place.")
    yield


app = FastAPI(
    title="Nexus CPG Intelligence API",
    description="Demand Profiling, Economic Profiling, Forecasting, and an AI Business Assistant over CPG POS data.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # local analyst tool — not exposed publicly; tighten if deployed
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(data.router)
app.include_router(overview.router)
app.include_router(demand.router)
app.include_router(economics.router)
app.include_router(forecasting.router)
app.include_router(recommendations.router)
app.include_router(llm.router)
app.include_router(reports.router)
