# Nexus CPG Intelligence

A CPG Demand Intelligence and Forecasting application: Demand Profiling, Economic Profiling, a multi-model Forecasting engine, and an LLM-powered Business Assistant, over retail POS data — with a FastAPI backend and a Streamlit frontend.

> The raw sample dataset's own documentation (file formats, data traps, scenario design) lives in [`nexus_cpg_sample_data_v1/README.md`](nexus_cpg_sample_data_v1/README.md) and is unchanged by this project. This file documents the application built on top of it.

## Architecture

```
nexus_engine/           Core analytical engine (no API/UI dependencies)
  ingest.py, clean.py, calendar.py, classify.py, economics.py   Demand + Economic Profiling (V1 / V1.1)
  pipeline.py, validate.py                                       Orchestration + answer-key validation
  forecasting/                                                   Forecasting engine (Module 3)
    models.py        Naive, Seasonal Naive, Moving Average, Holt-Winters, Auto-ARIMA (grid search),
                      Croston (SBA), LightGBM/Random Forest
    backtest.py       Chronological walk-forward model comparison
    metrics.py        MAE, RMSE, WAPE, MASE, Bias (zero/intermittent-demand safe)
    selector.py       Demand-class -> candidate model list (never forces every model on every SKU)
    features.py       Business-factor scaffold (Module 4): price-change history is real; everything
                       else (promo, marketing, competitor, weather, distribution, cannibalization) is
                       explicitly marked unavailable rather than invented
    forecast.py        run_forecast() orchestrator: the one entry point everything else calls

assistant/              LLM integration (Module 5)
  tools.py              The actual calculations the assistant can call — every number traces back to
                         nexus_engine; the LLM never invents one
  providers.py           Pluggable providers: MockProvider (free, rule-based, no key needed),
                         AnthropicProvider, OpenAIProvider (real tool-calling, need an API key)

api/                     FastAPI backend (Module 7)
  main.py, routers/*.py  health, data upload/validate/pipeline-run, demand, economics, forecast, llm, reports
  state.py               In-memory app state holding the loaded dataset + computed tables

frontend/                Streamlit frontend (Module 6)
  app.py, pages_impl/*.py   Overview, Data Management, Demand Profiling, Economic Profiling,
                            Forecasting, AI Business Assistant, Reports & Exports, Settings

tests/                   pytest suite (engine calculations + API)
scripts/                 Standalone smoke-test scripts (forecasting engine, API, frontend)
nexus_cpg_sample_data_v1/ Bundled sample dataset + answer_key/ (testing only — the engine never reads it)
```

The frontend talks to the backend only over HTTP — they're two separate processes, exactly like a real deployment.

## Install

Requires Python 3.11+.

```bash
cd "cpg forecast"
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run

**1. Start the backend** (loads the sample dataset and runs the pipeline automatically on startup):

```bash
source .venv/bin/activate
uvicorn api.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

**2. Start the frontend**, in a second terminal:

```bash
source .venv/bin/activate
streamlit run frontend/app.py
```

Frontend URL: **http://localhost:8501**

No API keys or external services are required to run the app as-is — the AI Business Assistant works out of the box in free, rule-based mode (see below).

## Configuration (environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `NEXUS_DATA_DIR` | `nexus_cpg_sample_data_v1/` | Raw-data directory the backend loads on startup |
| `NEXUS_OUTPUT_DIR` | `output/` | Where pipeline output CSVs are written |
| `NEXUS_ASOF` | `2026-11-20` | Analysis as-of date |
| `NEXUS_UPLOAD_DIR` | `uploaded_data/` | Where files uploaded via Data Management are saved |
| `NEXUS_API_URL` | `http://localhost:8000` | Backend URL the frontend calls |
| `NEXUS_LLM_PROVIDER` | `mock` | `mock` (free, rule-based) / `anthropic` / `openai` |
| `ANTHROPIC_API_KEY` | — | Required only if `NEXUS_LLM_PROVIDER=anthropic` |
| `OPENAI_API_KEY` | — | Required only if `NEXUS_LLM_PROVIDER=openai` |

The data directory, as-of date, and uploaded files can also be changed at runtime from the **Data Management** page (`POST /data/pipeline/run`) without restarting the server.

## The AI Business Assistant and LLM costs

By default (`NEXUS_LLM_PROVIDER=mock`), the assistant runs with **no API key and no cost**: it matches your question to one of ~14 known analyses via keyword routing, then explains the real computed result. This is pattern-matching, not language understanding — it only recognizes question shapes close to the built-in examples.

To get real natural-language understanding, free-form follow-up questions, and genuine hypothesis generation, set (before starting the backend):

```bash
export NEXUS_LLM_PROVIDER=anthropic
export ANTHROPIC_API_KEY=sk-ant-...
```
or
```bash
export NEXUS_LLM_PROVIDER=openai
export OPENAI_API_KEY=sk-...
```

Both are paid, usage-based APIs — you provide your own key and are billed by the provider directly; this project has no markup and no other cost. In every mode, the LLM only ever *calls* `nexus_engine` functions and explains their output — it cannot and does not produce a number on its own. **This path (real Anthropic/OpenAI tool-calling) is implemented but not exercised in this environment**, since no key was available while building it; the `mock` path has been tested end-to-end.

## Running tests

```bash
source .venv/bin/activate
python3 -m pytest -q                              # 47 tests: engine calculations + API
python3 run_pipeline.py                           # original demand/economic pipeline + answer-key validation
python3 scripts/test_forecasting_standalone.py    # forecasting engine across every demand class
python3 scripts/test_api_smoke.py                 # full API walkthrough
python3 scripts/test_frontend_apptest.py          # all 8 frontend pages render (needs backend running)
python3 scripts/test_frontend_interactions.py     # forecast-generation + assistant button clicks (needs backend running)
```

## Known limitations

- **Business factors** (Module 4): only price-change history is real (derived from `sku_economics.csv`). Promotions, marketing, competitor activity, weather, distribution changes, and cannibalization have no data source in this dataset and are reported as explicitly unavailable (`GET /forecast/business-factors`) rather than estimated.
- **Price-elasticity scenarios**: never auto-applied. `POST /forecast/scenario` returns the baseline forecast unchanged unless you supply an explicit elasticity assumption.
- **Hierarchy support**: forecasting works at SKU x store grain, matching the data. There is no factory-level or category-level data in this dataset, so no hierarchical reconciliation is implemented or claimed.
- **Auto-ARIMA** is a small grid search over `statsmodels.SARIMAX`, not `pmdarima`'s `auto_arima` — labeled as such in the UI and API (`"Auto-ARIMA (grid search)"`).
- **Prediction intervals**: labeled `model_native` (Holt-Winters/SARIMAX's own fitted distribution) or `approximate` (a residual-spread heuristic for models with no native interval, e.g. Naive/Moving Average). Croston and the ML regressor expose point forecasts only.
- The Anthropic/OpenAI LLM provider code paths are implemented but untested live in this environment (no API key available). The `mock` provider is fully tested.
