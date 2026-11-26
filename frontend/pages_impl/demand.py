import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import components
from api_client import APIError, get
from theme import ACCENT_CYAN, CLASS_COLORS, CRITICAL, apply_theme

CLASS_TONE = {"SMOOTH": "cyan", "ERRATIC": "warning", "INTERMITTENT": "purple", "LUMPY": "critical", "DORMANT": "neutral", "NOT_RANGED": "neutral", "INSUFFICIENT": "neutral"}


def _explain_classification(r: dict) -> str:
    cls, adi, cv2, N, K, conf = r.get("demand_class_90d"), r.get("adi_90d"), r.get("cv2_90d"), r.get("N_90d"), r.get("K_90d"), r.get("confidence_90d")
    if cls == "NOT_RANGED":
        return "Not currently ranged at this store — no valid selling days in the last 90 days, so no classification applies."
    if cls == "DORMANT":
        return f"Ranged and reporting for {N:.0f} valid days, but **zero sales** in that window — classified DORMANT, not simply low-demand."
    if cls in ("INSUFFICIENT", None):
        return f"Only {K:.0f} positive-demand day(s) observed — not enough to estimate variance reliably."
    adi_desc = "frequent" if adi < 1.32 else "infrequent"
    cv2_desc = "low, predictable" if cv2 < 0.49 else "high, volatile"
    conf_desc = "based on a solid sample" if conf == "HIGH" else "but treat it as provisional — the sample is still thin"
    return (
        f"**ADI = {adi:.2f}** ({adi_desc} demand — avg. {adi:.1f} days between sales) and "
        f"**CV² = {cv2:.2f}** ({cv2_desc} order sizes) place this SKU in the **{cls}** quadrant. "
        f"Confidence is **{conf}** ({conf_desc}), from {K:.0f} positive days out of {N:.0f} valid days."
    )


def render():
    components.page_header("Demand Profiling", "ADI/CV² classification, trend, seasonality, and stockout exposure per SKU × store.", icon="📈")
    try:
        skus = get("/demand/skus")
    except APIError as exc:
        st.warning(f"Run the pipeline first (Data Management page). {exc}")
        return

    sku_df = pd.DataFrame(skus)

    components.section_title("Filters", "🔎")
    c1, c2, c3 = st.columns(3)
    with c1:
        store_filter = st.selectbox("Store", ["All"] + sorted(sku_df["store_id"].unique()))
    with c2:
        category_filter = st.selectbox("Category", ["All"] + sorted(sku_df["category"].dropna().unique()))
    with c3:
        class_filter = st.selectbox("Demand class", ["All", "SMOOTH", "ERRATIC", "INTERMITTENT", "LUMPY", "DORMANT", "NOT_RANGED", "INSUFFICIENT"])

    params = {}
    if store_filter != "All":
        params["store_id"] = store_filter
    if category_filter != "All":
        params["category"] = category_filter
    if class_filter != "All":
        params["demand_class"] = class_filter

    profile = pd.DataFrame(get("/demand/profile", params=params))
    if profile.empty:
        st.info("No series match these filters.")
        return

    components.kpi_row([
        {"label": "Series shown", "value": len(profile), "icon": "🧮", "tone": "info"},
        {"label": "Declining (90D)", "value": int((profile["trend_direction_90d"] == "DECLINING").sum()), "icon": "📉", "tone": "warning"},
        {"label": "Regime shifts", "value": int((profile["regime_shift_detected"] == True).sum()), "icon": "🔀", "tone": "critical"},  # noqa: E712
        {"label": "Stockout days (sum)", "value": int(profile["oos_days_90d"].fillna(0).sum()), "icon": "🚨", "tone": "warning"},
    ])

    col1, col2 = st.columns([1, 2])
    with col1:
        components.section_title("90D Classification Mix", "📊")
        counts = profile["demand_class_90d"].value_counts()
        fig = px.pie(names=counts.index, values=counts.values, color=counts.index, color_discrete_map=CLASS_COLORS, hole=0.55)
        fig.update_traces(textfont_color="#EDEFF7", marker=dict(line=dict(color="#0A0E1A", width=2)))
        apply_theme(fig)
        fig.update_layout(height=320)
        st.plotly_chart(fig, width="stretch")
    with col2:
        components.section_title("SKU-Level Demand Table (90D)", "📋")
        show_cols = ["store_id", "sku_code", "N_90d", "K_90d", "velocity_90d", "adi_90d", "cv2_90d",
                     "demand_class_90d", "confidence_90d", "trend_direction_90d", "oos_days_90d", "regime_shift_detected"]
        st.dataframe(profile[show_cols], width="stretch", hide_index=True, height=320)

    components.divider_label("90-Day vs 365-Day Comparison")
    compare_cols = ["store_id", "sku_code", "demand_class_90d", "demand_class_365d", "velocity_90d", "velocity_365d",
                    "trend_direction_90d", "trend_direction_365d", "weekly_seasonality_strength", "annual_seasonality_strength", "regime_shift_detected"]
    st.dataframe(profile[compare_cols], width="stretch", hide_index=True)

    shifted = profile[profile["regime_shift_detected"] == True]  # noqa: E712
    if not shifted.empty:
        components.insight_panel(
            "Regime-shift alert",
            f"{len(shifted)} series show a 90-day classification that disagrees with their 365-day classification — a real pattern change, not noise: " +
            ", ".join(f"<b>{r.sku_code}</b> @ {r.store_id} ({r.demand_class_90d} vs {r.demand_class_365d})" for r in shifted.itertuples()),
            icon="🔀",
        )

    components.divider_label("Actual Demand — Series Detail")
    c1, c2 = st.columns(2)
    with c1:
        sel_store = st.selectbox("Store", sorted(profile["store_id"].unique()), key="series_store")
    with c2:
        sku_options = sorted(profile[profile["store_id"] == sel_store]["sku_code"].unique())
        sel_sku = st.selectbox("SKU", sku_options, key="series_sku")

    row = profile[(profile["store_id"] == sel_store) & (profile["sku_code"] == sel_sku)]
    if not row.empty:
        r = row.iloc[0].to_dict()
        tone = CLASS_TONE.get(r["demand_class_90d"], "neutral")
        components.kpi_row([
            {"label": "90D Class", "value": r["demand_class_90d"], "icon": "🏷️", "tone": tone},
            {"label": "Confidence", "value": r["confidence_90d"], "icon": "🎯", "tone": "positive" if r["confidence_90d"] == "HIGH" else "warning"},
            {"label": "Trend (90D)", "value": r["trend_direction_90d"], "icon": "📈", "tone": "warning" if r["trend_direction_90d"] == "DECLINING" else "positive"},
            {"label": "Stockout days (90D)", "value": int(r["oos_days_90d"]) if pd.notna(r["oos_days_90d"]) else 0, "icon": "🚨", "tone": "warning" if (r["oos_days_90d"] or 0) > 0 else "positive"},
        ])
        components.insight_panel("Why this classification?", _explain_classification(r), icon="🧭")

    series = pd.DataFrame(get("/demand/series", params={"store_id": sel_store, "sku_code": sel_sku}))
    if not series.empty:
        series["date"] = pd.to_datetime(series["date"])
        fig = go.Figure()
        valid = series[series["valid_day"]]
        fig.add_trace(go.Scatter(x=valid["date"], y=valid["sold_ea"], mode="lines", name="Sold (EA)", line=dict(color=ACCENT_CYAN, width=2)))
        stockouts = series[series["stockout_flag"] == True]  # noqa: E712
        if not stockouts.empty:
            fig.add_trace(go.Scatter(x=stockouts["date"], y=stockouts["sold_ea"], mode="markers", name="Stockout day", marker=dict(color=CRITICAL, size=7, symbol="x")))
        apply_theme(fig)
        fig.update_layout(height=380, title=f"{sel_sku} @ {sel_store} — daily sold units (valid days only)")
        st.plotly_chart(fig, width="stretch")
