"""The actual tools the assistant can call. Every number a user sees comes
from one of these functions reading the pipeline's computed tables (or
running a real forecast) — never from the LLM itself. Each entry in
``TOOLS`` pairs a JSON-schema description (for real LLM function-calling)
with the Python function that does the work, so both the real-provider
path and the rule-based fallback path call the exact same code.
"""
from __future__ import annotations

import pandas as pd

from nexus_engine.util import df_to_records

from nexus_engine.forecasting import recommend_for_series, run_forecast


def _demand(state) -> pd.DataFrame:
    return state.tables["demand_profile"]


def _econ(state) -> pd.DataFrame:
    return state.tables["economic_profile"]


def _supplier(state) -> pd.DataFrame:
    return state.tables["supplier_profile"]


def declining_demand(state, store_id: str | None = None, top_n: int = 10) -> dict:
    df = _demand(state)
    if store_id:
        df = df[df["store_id"] == store_id]
    out = df[df["trend_direction_90d"] == "DECLINING"][["store_id", "sku_code", "velocity_90d", "trend_score_90d", "demand_class_90d"]]
    out = out.sort_values("trend_score_90d").head(top_n)
    return {"rows": df_to_records(out), "note": "trend_direction_90d == DECLINING, sorted by most-negative trend_score_90d."}


def becoming_intermittent(state, store_id: str | None = None) -> dict:
    """SKUs whose demand pattern is shifting — flagged via the 90D-vs-365D regime-shift check."""
    df = _demand(state)
    if store_id:
        df = df[df["store_id"] == store_id]
    out = df[df["regime_shift_detected"] == True]  # noqa: E712
    cols = ["store_id", "sku_code", "demand_class_90d", "demand_class_365d"]
    return {"rows": df_to_records(out[cols]), "note": "demand_class_90d differs from demand_class_365d — a genuine pattern change, not noise."}


def unusual_demand_patterns(state, store_id: str | None = None) -> dict:
    """ERRATIC or LUMPY classified SKUs — hard to plan against with simple stock policies."""
    df = _demand(state)
    if store_id:
        df = df[df["store_id"] == store_id]
    out = df[df["demand_class_90d"].isin(["ERRATIC", "LUMPY"])][["store_id", "sku_code", "demand_class_90d", "adi_90d", "cv2_90d"]]
    return {"rows": df_to_records(out), "note": "demand_class_90d in {ERRATIC, LUMPY}."}


def stockout_exposure(state, top_n: int = 10) -> dict:
    df = _demand(state)
    out = df.sort_values("oos_days_90d", ascending=False).head(top_n)[["store_id", "sku_code", "oos_days_90d", "demand_class_90d"]]
    return {"rows": df_to_records(out), "note": "oos_days_90d = days flagged out-of-stock (inventory_daily.oos_eod_flag) in the last 90 valid days."}


def highest_gross_profit(state, top_n: int = 10) -> dict:
    econ = _econ(state)
    df = econ[econ["gm_per_ea"].notna()].copy()
    df["daily_gross_profit"] = (df["gm_per_ea"] * df["velocity_90d"]).round(2)
    out = df.sort_values("daily_gross_profit", ascending=False).head(top_n)[["store_id", "sku_code", "gm_per_ea", "gm_pct", "velocity_90d", "daily_gross_profit"]]
    return {"rows": df_to_records(out), "note": "daily_gross_profit = gm_per_ea * velocity_90d (estimated units/day). Not annualized."}


def slow_moving_high_moq(state, min_coverage_days: float = 60) -> dict:
    sup = _supplier(state)
    out = sup[(sup["moq_coverage_days"].notna()) & (sup["moq_coverage_days"] >= min_coverage_days)]
    out = out.sort_values("moq_coverage_days", ascending=False)[["sku_code", "supplier_id", "ship_to_location_id", "moq_coverage_days", "velocity_90d"]]
    return {"rows": df_to_records(out), "note": f"moq_coverage_days >= {min_coverage_days}: a single MOQ order covers that many days of expected demand."}


def moq_coverage_over(state, days: float = 90) -> dict:
    return slow_moving_high_moq(state, min_coverage_days=days)


def unfavorable_supplier_terms(state, sku_code: str | None = None) -> dict:
    """Compares suppliers of the same SKU side by side — never averaged, per trap #15."""
    sup = _supplier(state)
    if sku_code:
        sup = sup[sup["sku_code"] == sku_code]
    multi = sup[sup.duplicated("sku_code", keep=False)].sort_values(["sku_code", "unit_purchase_cost_per_ea"])
    cols = ["sku_code", "supplier_id", "unit_purchase_cost_per_ea", "lead_time_days", "moq_coverage_days", "shelf_life_days"]
    return {"rows": df_to_records(multi[cols]), "note": "SKUs with more than one active supplier, compared side by side (never averaged)."}


def high_margin_declining(state, top_n: int = 10) -> dict:
    demand = _demand(state)[["store_id", "sku_code", "trend_direction_90d", "demand_class_90d"]]
    econ = _econ(state)[["store_id", "sku_code", "gm_pct", "velocity_90d"]]
    m = demand.merge(econ, on=["store_id", "sku_code"])
    out = m[(m["trend_direction_90d"] == "DECLINING") & m["gm_pct"].notna()].sort_values("gm_pct", ascending=False).head(top_n)
    return {"rows": df_to_records(out), "note": "trend_direction_90d == DECLINING, ranked by gm_pct (gross margin %)."}


def high_moq_low_forecast(state, horizon: int = 30) -> dict:
    """Needs an actual forecast per SKU (not just current velocity) — runs
    the real forecasting engine, so this one is slower than the others.
    """
    demand = _demand(state)
    sup = _supplier(state)[["sku_code", "ship_to_location_id", "moq_coverage_days"]].rename(columns={"ship_to_location_id": "store_id"})
    candidates = demand[demand["demand_class_90d"] != "NOT_RANGED"][["store_id", "sku_code"]].drop_duplicates()

    rows = []
    for r in candidates.itertuples(index=False):
        try:
            fc = run_forecast(state.tables["daily_panel"], state.tables["demand_profile"], r.store_id, r.sku_code, horizon=horizon, frequency="D", n_folds=2)
        except ValueError:
            continue
        rows.append({"store_id": r.store_id, "sku_code": r.sku_code, "forecast_mean_daily": round(sum(fc.forecast_values) / len(fc.forecast_values), 3), "model": fc.selected_model})

    fc_df = pd.DataFrame(rows).merge(sup, on=["store_id", "sku_code"], how="left")
    out = fc_df[fc_df["moq_coverage_days"] > 30].sort_values("forecast_mean_daily").head(10)
    return {"rows": df_to_records(out), "note": "forecast_mean_daily is the mean of a fresh forecast run (horizon days), compared against existing MOQ coverage. moq_coverage_days > 30 shown; low forecast_mean_daily flags overexposure risk."}


def forecast_for_sku(state, store_id: str, sku_code: str, horizon: int = 30, frequency: str = "D", model: str | None = None) -> dict:
    fc = run_forecast(state.tables["daily_panel"], state.tables["demand_profile"], store_id, sku_code, horizon=horizon, frequency=frequency, model_override=model)
    return {
        "selected_model": fc.selected_model, "selected_by": fc.selected_by, "demand_class": fc.demand_class,
        "trend": fc.trend, "forecast_values": fc.forecast_values, "forecast_dates": fc.forecast_dates,
        "comparison": [{"model": c["model_name"], "metrics": c["metrics"]} for c in fc.comparison],
        "summary": fc.summary, "warnings": fc.warnings,
    }


def best_model_for_sku(state, store_id: str, sku_code: str) -> dict:
    """Backed by the same shortlist-then-backtest recommendation engine used
    in the SKU Intelligence page — not a separate, potentially-disagreeing
    calculation.
    """
    rec = recommend_for_series(state.tables["daily_panel"], state.tables["demand_profile"], store_id, sku_code, horizon=14, frequency="D", n_folds=2)
    return {
        "status": rec.status, "best_model": rec.recommended_model_name, "confidence": rec.confidence,
        "reason": rec.reason, "alternatives": rec.alternative_models,
        "comparison": [{"model": c["model_name"], "metrics": c["metrics"]} for c in rec.comparison],
        "data_limitations": rec.data_limitations,
        "note": "Shortlisted from the SKU's demand profile (not demand class alone), ranked by lowest backtest WAPE (fallback MASE/MAE) over chronological walk-forward folds.",
    }


def why_model_selected(state, store_id: str, sku_code: str) -> dict:
    """For 'why was <model> selected for this product?' — answers with the
    actual recommendation, regardless of which model the question names.
    """
    return best_model_for_sku(state, store_id, sku_code)


def insufficient_data_skus(state, store_id: str | None = None) -> dict:
    """Requires the bulk recommendation sweep — computes it on demand (and
    caches it) if it hasn't been run yet for this dataset.
    """
    if state.recommendations is None:
        state.compute_recommendations()
    df = state.recommendations
    if store_id:
        df = df[df["store_id"] == store_id]
    out = df[df["status"] == "INSUFFICIENT_DATA"][["store_id", "sku_code", "demand_class", "available_history_days", "reason"]]
    return {"rows": df_to_records(out), "note": "status == INSUFFICIENT_DATA: not enough history for any shortlisted model to be evaluated reliably — no forecast is generated for these."}


def best_overall_model(state) -> dict:
    """Aggregates across every RECOMMENDED series: which model wins most
    often, and how it performs on average (by WAPE where available).
    """
    if state.recommendations is None:
        state.compute_recommendations()
    df = state.recommendations[state.recommendations["status"] == "RECOMMENDED"]
    if df.empty:
        return {"rows": [], "note": "No series have a RECOMMENDED status yet."}
    counts = df["recommended_model_name"].value_counts()
    avg_wape = df.groupby("recommended_model_name")["best_wape"].mean().round(4)
    out = pd.DataFrame({"model": counts.index, "times_recommended": counts.values}).merge(
        avg_wape.rename("avg_wape_when_recommended").reset_index().rename(columns={"recommended_model_name": "model"}), on="model", how="left")
    out = out.sort_values("times_recommended", ascending=False)
    return {"rows": df_to_records(out), "note": "times_recommended = how many series this model won the backtest comparison for; avg_wape_when_recommended is only over the series where WAPE was computable."}


def increasing_demand_skus(state, store_id: str | None = None, top_n: int = 10) -> dict:
    df = _demand(state)
    if store_id:
        df = df[df["store_id"] == store_id]
    out = df[df["trend_direction_90d"] == "INCREASING"][["store_id", "sku_code", "velocity_90d", "trend_score_90d", "demand_class_90d"]]
    out = out.sort_values("trend_score_90d", ascending=False).head(top_n)
    return {"rows": df_to_records(out), "note": "trend_direction_90d == INCREASING, sorted by most-positive trend_score_90d."}


def forecast_for_store(state, store_id: str, horizon: int = 30) -> dict:
    """'Show me the forecast for all products in STORE-X' — one forecast per
    eligible SKU in that store, each using its own recommended model.
    """
    if state.recommendations is None:
        state.compute_recommendations()
    eligible = state.recommendations[(state.recommendations["store_id"] == store_id) & (state.recommendations["status"] == "RECOMMENDED")]
    rows = []
    for r in eligible.itertuples(index=False):
        try:
            fc = run_forecast(state.tables["daily_panel"], state.tables["demand_profile"], store_id, r.sku_code, horizon=horizon, frequency="D", model_override=r.recommended_model)
        except ValueError:
            continue
        rows.append({"sku_code": r.sku_code, "model": fc.selected_model, "demand_class": fc.demand_class,
                      "avg_daily_forecast": round(sum(fc.forecast_values) / len(fc.forecast_values), 3), "trend": fc.trend})
    return {"rows": rows, "note": f"One forecast per eligible SKU at {store_id} (status=RECOMMENDED only), each using its own recommended model, horizon={horizon} days."}


def major_risks(state) -> dict:
    declining = declining_demand(state, top_n=5)["rows"]
    high_moq = slow_moving_high_moq(state, min_coverage_days=90)["rows"]
    stockouts = stockout_exposure(state, top_n=5)["rows"]
    missing_fin = _econ(state)
    missing_fin = df_to_records(missing_fin[missing_fin["gm_issue"].notna() | missing_fin["gmroi_issue"].notna()][["store_id", "sku_code", "gm_issue", "gmroi_issue"]])
    return {
        "declining_demand": declining, "high_moq_exposure": high_moq,
        "stockout_exposure": stockouts, "missing_financial_data": missing_fin,
        "note": "Each list is independently computed; a SKU can appear in more than one.",
    }


def priority_products(state, top_n: int = 10) -> dict:
    """High margin + stable-or-growing demand + not already overexposed on MOQ — a simple, transparent composite, not a learned ranking."""
    demand = _demand(state)[["store_id", "sku_code", "trend_direction_90d", "demand_class_90d", "velocity_90d"]]
    econ = _econ(state)[["store_id", "sku_code", "gm_pct"]]
    sup = _supplier(state).groupby(["sku_code", "ship_to_location_id"])["moq_coverage_days"].max().reset_index().rename(columns={"ship_to_location_id": "store_id"})
    m = demand.merge(econ, on=["store_id", "sku_code"]).merge(sup, on=["store_id", "sku_code"], how="left")
    ok = m[(m["trend_direction_90d"].isin(["STABLE", "INCREASING"])) & (m["demand_class_90d"].isin(["SMOOTH", "ERRATIC"])) & (m["gm_pct"].notna()) & ((m["moq_coverage_days"].isna()) | (m["moq_coverage_days"] < 60))]
    out = ok.sort_values("gm_pct", ascending=False).head(top_n)
    return {"rows": df_to_records(out), "note": "Composite filter: stable/increasing trend, SMOOTH/ERRATIC class, known margin, MOQ coverage under 60 days. Not a predictive score."}


TOOLS = [
    {"name": "declining_demand", "description": "SKUs with a declining 90-day demand trend.", "fn": declining_demand,
     "parameters": {"store_id": {"type": "string", "required": False}, "top_n": {"type": "integer", "required": False}}},
    {"name": "becoming_intermittent", "description": "SKUs whose demand pattern recently shifted (regime-shift flag).", "fn": becoming_intermittent,
     "parameters": {"store_id": {"type": "string", "required": False}}},
    {"name": "unusual_demand_patterns", "description": "SKUs classified ERRATIC or LUMPY.", "fn": unusual_demand_patterns,
     "parameters": {"store_id": {"type": "string", "required": False}}},
    {"name": "stockout_exposure", "description": "SKUs with the most out-of-stock days in the last 90 days.", "fn": stockout_exposure,
     "parameters": {"top_n": {"type": "integer", "required": False}}},
    {"name": "highest_gross_profit", "description": "SKUs generating the highest estimated daily gross profit.", "fn": highest_gross_profit,
     "parameters": {"top_n": {"type": "integer", "required": False}}},
    {"name": "slow_moving_high_moq", "description": "SKUs where one MOQ order covers more than N days of demand.", "fn": slow_moving_high_moq,
     "parameters": {"min_coverage_days": {"type": "number", "required": False}}},
    {"name": "moq_coverage_over", "description": "SKUs with MOQ coverage greater than N days.", "fn": moq_coverage_over,
     "parameters": {"days": {"type": "number", "required": False}}},
    {"name": "unfavorable_supplier_terms", "description": "Side-by-side supplier comparison for SKUs with more than one supplier.", "fn": unfavorable_supplier_terms,
     "parameters": {"sku_code": {"type": "string", "required": False}}},
    {"name": "high_margin_declining", "description": "High-margin products whose demand is declining.", "fn": high_margin_declining,
     "parameters": {"top_n": {"type": "integer", "required": False}}},
    {"name": "high_moq_low_forecast", "description": "SKUs with high MOQ coverage AND low forecast demand (runs a real forecast — slower).", "fn": high_moq_low_forecast,
     "parameters": {"horizon": {"type": "integer", "required": False}}},
    {"name": "forecast_for_sku", "description": "Generate a demand forecast for one store/SKU.", "fn": forecast_for_sku,
     "parameters": {"store_id": {"type": "string", "required": True}, "sku_code": {"type": "string", "required": True}, "horizon": {"type": "integer", "required": False}, "frequency": {"type": "string", "required": False}, "model": {"type": "string", "required": False}}},
    {"name": "best_model_for_sku", "description": "Which forecasting model performs best for a given SKU, with the comparison table and the reason for the recommendation.", "fn": best_model_for_sku,
     "parameters": {"store_id": {"type": "string", "required": True}, "sku_code": {"type": "string", "required": True}}},
    {"name": "why_model_selected", "description": "Explains why a particular forecasting model was recommended for a SKU.", "fn": why_model_selected,
     "parameters": {"store_id": {"type": "string", "required": True}, "sku_code": {"type": "string", "required": True}}},
    {"name": "insufficient_data_skus", "description": "SKUs with too little history for a reliable forecasting-model recommendation.", "fn": insufficient_data_skus,
     "parameters": {"store_id": {"type": "string", "required": False}}},
    {"name": "best_overall_model", "description": "Which forecasting model is recommended most often across the whole portfolio, and how it performs on average.", "fn": best_overall_model, "parameters": {}},
    {"name": "increasing_demand_skus", "description": "SKUs with an increasing 90-day demand trend.", "fn": increasing_demand_skus,
     "parameters": {"store_id": {"type": "string", "required": False}, "top_n": {"type": "integer", "required": False}}},
    {"name": "forecast_for_store", "description": "Forecast for every eligible product in one store, each using its own recommended model.", "fn": forecast_for_store,
     "parameters": {"store_id": {"type": "string", "required": True}, "horizon": {"type": "integer", "required": False}}},
    {"name": "major_risks", "description": "Cross-module summary of the biggest demand and profitability risks.", "fn": major_risks, "parameters": {}},
    {"name": "priority_products", "description": "Products to prioritize: healthy margin, stable/growing demand, not overexposed on MOQ.", "fn": priority_products,
     "parameters": {"top_n": {"type": "integer", "required": False}}},
]

TOOLS_BY_NAME = {t["name"]: t for t in TOOLS}
