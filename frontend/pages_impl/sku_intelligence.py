import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import components
from api_client import APIError, get, post
from theme import ACCENT_BLUE, ACCENT_CYAN, ACCENT_PURPLE, apply_theme

SEASONALITY_THRESHOLD = 0.3


def _seasonality_label(row) -> str:
    annual = row.get("annual_seasonality_strength")
    weekly = row.get("weekly_seasonality_strength")
    if pd.notna(annual) and annual >= SEASONALITY_THRESHOLD:
        return "Annual"
    if pd.notna(weekly) and weekly >= SEASONALITY_THRESHOLD:
        return "Weekly"
    return "None detected"


def render():
    components.page_header("SKU Intelligence & Model Recommendations", "Automated demand profiling and explainable forecast-model selection for every SKU x store.", icon="🧠")

    try:
        profile = pd.DataFrame(get("/demand/profile"))
        skus = pd.DataFrame(get("/demand/skus"))
    except APIError as exc:
        st.warning(f"Run the pipeline first (Data Management page). {exc}")
        return

    profile = profile.merge(skus[["store_id", "sku_code", "description", "category"]], on=["store_id", "sku_code"], how="left")
    profile["seasonality"] = profile.apply(_seasonality_label, axis=1)

    # ---------------- A. SKU Profiling Overview ----------------
    components.section_title("A. SKU Profiling Overview", "📋")
    counts = profile["demand_class_90d"].value_counts()
    components.kpi_row([
        {"label": "Total SKUs", "value": int(skus["sku_code"].nunique()), "icon": "📦", "tone": "info"},
        {"label": "Total Stores", "value": int(skus["store_id"].nunique()), "icon": "🏬", "tone": "info"},
        {"label": "Series Analyzed", "value": len(profile), "icon": "🧮", "tone": "cyan"},
        {"label": "Smooth", "value": int(counts.get("SMOOTH", 0)), "icon": "📈", "tone": "cyan"},
        {"label": "Erratic", "value": int(counts.get("ERRATIC", 0)), "icon": "📊", "tone": "warning"},
    ])
    components.kpi_row([
        {"label": "Intermittent", "value": int(counts.get("INTERMITTENT", 0)), "icon": "🔹", "tone": "purple"},
        {"label": "Lumpy", "value": int(counts.get("LUMPY", 0)), "icon": "⚡", "tone": "critical"},
        {"label": "Declining Demand", "value": int((profile["trend_direction_90d"] == "DECLINING").sum()), "icon": "📉", "tone": "warning"},
        {"label": "Seasonal SKUs", "value": int((profile["seasonality"] != "None detected").sum()), "icon": "🍂", "tone": "info"},
        {"label": "Insufficient-Data Series", "value": int(profile["demand_class_90d"].isin(["INSUFFICIENT", "NOT_RANGED"]).sum()), "icon": "⚠️", "tone": "warning"},
    ])

    # ---------------- B. SKU-Level Profile Table ----------------
    components.divider_label("B. SKU-Level Profile Table")
    c1, c2, c3 = st.columns(3)
    with c1:
        store_filter = st.selectbox("Store", ["All"] + sorted(profile["store_id"].unique()), key="ski_store")
    with c2:
        class_filter = st.selectbox("Demand class", ["All"] + sorted(profile["demand_class_90d"].unique()), key="ski_class")
    with c3:
        search = st.text_input("Search SKU or product name", key="ski_search")

    view = profile.copy()
    if store_filter != "All":
        view = view[view["store_id"] == store_filter]
    if class_filter != "All":
        view = view[view["demand_class_90d"] == class_filter]
    if search:
        mask = view["sku_code"].str.contains(search, case=False, na=False) | view["description"].str.contains(search, case=False, na=False)
        view = view[mask]

    profile_cols = {
        "sku_code": "SKU", "description": "Product Name", "store_id": "Store", "velocity_90d": "Avg Daily Sales",
        "adi_90d": "ADI", "cv2_90d": "CV²", "demand_class_90d": "Demand Class", "trend_direction_90d": "Trend",
        "seasonality": "Seasonality", "confidence_90d": "Profile Confidence",
    }
    st.dataframe(view[list(profile_cols)].rename(columns=profile_cols), width="stretch", hide_index=True)

    with st.expander("Why these classifications? (business interpretation)"):
        for r in view.itertuples():
            st.markdown(f"**{r.sku_code} @ {r.store_id}** — {getattr(r, 'business_interpretation_90d', '')}")

    # ---------------- C. Model Recommendation Table ----------------
    components.divider_label("C. Model Recommendation Table")
    st.caption("Shortlists candidate models from each SKU's profile (not demand class alone), evaluates them with chronological backtesting, and explains the pick. Computed on demand — this sweeps every series x several models, so it takes a few seconds to a few minutes depending on dataset size.")

    rec_status = get("/recommendations/status")
    c1, c2 = st.columns([1, 3])
    with c1:
        if st.button("🔍 Analyze All SKUs & Recommend Models", type="primary"):
            with st.spinner("Profiling every SKU and backtesting candidate models... this can take a while for large datasets."):
                try:
                    result = post("/recommendations/compute", json=None)
                except APIError as exc:
                    st.error(str(exc))
                else:
                    st.success(f"Analyzed {result['series_count']} series — {result['status_counts']}")
                    st.rerun()
    with c2:
        if rec_status["computed"]:
            st.caption(f"Last computed: {rec_status['computed_at']} · {rec_status['series_count']} series" + (" · **stale, dataset changed since**" if rec_status["stale"] else ""))
        else:
            st.caption("Not yet computed for this dataset.")

    if not rec_status["computed"]:
        st.info("Click **Analyze All SKUs & Recommend Models** to generate the recommendation table.")
        return

    recs = pd.DataFrame(get("/recommendations"))
    rec_cols = {
        "sku_code": "SKU", "store_id": "Store", "demand_class": "Demand Class", "recommended_model_name": "Recommended Model",
        "best_metric": "Best Evaluation Metric", "alternative_model": "Alternative Model", "reason": "Recommendation Reason",
        "status": "Recommendation Status",
    }
    st.dataframe(recs[list(rec_cols)].rename(columns=rec_cols), width="stretch", hide_index=True, height=360)

    insufficient = recs[recs["status"] == "INSUFFICIENT_DATA"]
    if not insufficient.empty:
        components.insight_panel(
            "Some SKUs don't have enough history for a reliable model yet",
            "<br>".join(f"<b>{r.sku_code}</b> @ {r.store_id}: {r.reason}" for r in insufficient.itertuples()),
            icon="⚠️",
        )

    # ---------------- D. Model Comparison ----------------
    components.divider_label("D. Model Comparison")
    recommended_only = recs[recs["status"] == "RECOMMENDED"]
    if recommended_only.empty:
        st.info("No series have a RECOMMENDED status yet.")
    else:
        c1, c2 = st.columns(2)
        with c1:
            cmp_store = st.selectbox("Store", sorted(recommended_only["store_id"].unique()), key="cmp_store")
        with c2:
            cmp_sku = st.selectbox("SKU", sorted(recommended_only[recommended_only["store_id"] == cmp_store]["sku_code"].unique()), key="cmp_sku")

        # Reuse the exact same horizon/folds the bulk table (section C) was
        # computed with, so this comparison can't silently disagree with the
        # row a user just saw there for the same SKU.
        bulk_params = rec_status.get("params") or {"horizon": 14, "frequency": "D", "n_folds": 2}
        detail = get(f"/recommendations/{cmp_store}/{cmp_sku}", params=bulk_params)
        comp_rows = []
        for c in detail["comparison"]:
            m = c["metrics"] or {}
            comp_rows.append({"Model": c["model_name"], "MAE": m.get("mae"), "RMSE": m.get("rmse"), "WAPE": m.get("wape"),
                               "MASE": m.get("mase"), "Bias": m.get("bias"),
                               "Best": "⭐" if c["model_key"] == detail["recommended_model"] else ""})
        st.dataframe(pd.DataFrame(comp_rows).sort_values("Best", ascending=False), width="stretch", hide_index=True)
        components.insight_panel("Why this model", detail["reason"], icon="🧭")
        c1, c2, c3 = st.columns(3)
        c1.metric("Recommended model", detail["recommended_model_name"])
        c2.metric("Confidence", detail["confidence"])
        c3.metric("Status", detail["status"])

        try:
            fc = post("/forecast/run", json={"store_id": cmp_store, "sku_code": cmp_sku, "horizon": bulk_params["horizon"], "frequency": bulk_params["frequency"], "model": detail["recommended_model"]})
        except APIError as exc:
            st.warning(str(exc))
        else:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=fc["history_dates"][-120:], y=fc["history_actual"][-120:], mode="lines", name="Actual", line=dict(color=ACCENT_CYAN)))
            fig.add_trace(go.Scatter(x=fc["forecast_dates"], y=fc["forecast_values"], mode="lines", name="Predicted", line=dict(color=ACCENT_PURPLE, dash="dash")))
            apply_theme(fig)
            fig.update_layout(height=380, title=f"Actual vs Predicted — {cmp_sku} @ {cmp_store} ({detail['recommended_model_name']})")
            st.plotly_chart(fig, width="stretch")

    # ---------------- E. Bulk Forecast Generation ----------------
    components.divider_label("E. Bulk Forecast Generation")
    st.caption("Generates a forecast for every eligible (RECOMMENDED-status) SKU x store, each using its own recommended model.")
    c1, c2, c3 = st.columns(3)
    with c1:
        bulk_store = st.selectbox("Store filter", ["All stores"] + sorted(recs["store_id"].unique()), key="bulk_store")
    with c2:
        bulk_horizon = st.selectbox("Horizon (days)", [7, 30, 60, 90, 180], index=1, key="bulk_horizon")
    with c3:
        st.write("")
        st.write("")
        run_bulk = st.button("⚙️ Generate Forecasts for All Eligible SKUs", type="primary")

    if run_bulk:
        payload = {"horizon": bulk_horizon, "frequency": "D"}
        if bulk_store != "All stores":
            payload["store_id"] = bulk_store
        with st.spinner("Generating forecasts..."):
            try:
                summary = post("/forecast/bulk", json=payload)
            except APIError as exc:
                st.error(str(exc))
            else:
                st.session_state["_bulk_forecast_summary"] = summary
                st.success(f"Forecasted {summary['series_forecasted']} series ({summary['total_rows']} forecast rows).")
                if summary["series_skipped"]:
                    st.warning(f"Skipped {len(summary['series_skipped'])} series: {summary['series_skipped']}")

    if st.session_state.get("_bulk_forecast_summary"):
        bulk_df = pd.DataFrame(get("/forecast/bulk/results"))
        if not bulk_df.empty:
            agg = bulk_df.groupby(["store_id", "sku_code", "model", "demand_class"], as_index=False)["forecast_value"].mean().rename(columns={"forecast_value": "avg_daily_forecast"})
            st.dataframe(agg, width="stretch", hide_index=True)
            from api_client import BASE_URL, get_raw
            csv_bytes = get_raw("/reports/export/bulk_forecast", params={"format": "csv"}).content
            st.download_button("⬇ Download full bulk forecast (CSV)", csv_bytes, file_name="bulk_forecast.csv", mime="text/csv")
