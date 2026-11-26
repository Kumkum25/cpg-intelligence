import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import components
from api_client import APIError, get, post
from theme import CLASS_COLORS, CRITICAL, SUCCESS, WARNING, apply_theme


def _tone_for(count: int, warn_at: int, crit_at: int) -> str:
    if count >= crit_at:
        return "critical"
    if count >= warn_at:
        return "warning"
    return "positive"


def render():
    components.page_header("Executive Overview", "Portfolio-wide demand, profitability, and risk — refreshed from the active dataset.", icon="📊")
    try:
        ov = get("/overview")
    except APIError as exc:
        st.warning(f"No pipeline results yet. Go to **Data Management** and run the pipeline. ({exc})")
        return

    st.caption(f"Analysis as of {ov['asof']}")

    components.kpi_row([
        {"label": "Total SKUs", "value": ov["total_skus"], "icon": "📦", "tone": "info"},
        {"label": "Total Stores", "value": ov["total_stores"], "icon": "🏬", "tone": "info"},
        {"label": "Demand Series", "value": ov["total_series"], "icon": "🧮", "tone": "info", "sub": "SKU × Store"},
        {"label": "Lifetime Units Sold", "value": f"{ov['total_units_sold_lifetime']:,.0f}", "icon": "🧾", "tone": "cyan"},
        {"label": "Avg Daily Velocity", "value": f"{ov['avg_daily_demand_velocity']:.1f}" if ov["avg_daily_demand_velocity"] else "—", "icon": "⚡", "tone": "cyan", "sub": "units / series / day"},
    ])
    components.kpi_row([
        {"label": "Est. Daily Gross Profit", "value": f"${ov['total_estimated_daily_gross_profit']:,.0f}", "icon": "💵", "tone": "positive"},
        {"label": "Declining-Trend SKUs", "value": ov["declining_sku_count"], "icon": "📉", "tone": _tone_for(ov["declining_sku_count"], 3, 8)},
        {"label": "Regime-Shift Alerts", "value": ov["regime_shift_count"], "icon": "🔀", "tone": _tone_for(ov["regime_shift_count"], 1, 3)},
        {"label": "Stockout-Exposed SKUs", "value": ov["stockout_exposed_count"], "icon": "🚨", "tone": _tone_for(ov["stockout_exposed_count"], 1, 4)},
        {"label": "High MOQ-Risk Lines", "value": ov["high_moq_risk_count"], "icon": "📦", "tone": _tone_for(ov["high_moq_risk_count"], 3, 8)},
    ])

    st.html("<div style='height:4px;'></div>")
    col1, col2 = st.columns([1, 1])
    with col1:
        components.section_title("Demand Classification Mix (90D)", "📈")
        counts = ov["demand_class_counts_90d"]
        df = pd.DataFrame({"class": list(counts.keys()), "count": list(counts.values())})
        fig = px.pie(df, names="class", values="count", color="class", color_discrete_map=CLASS_COLORS, hole=0.58)
        fig.update_traces(textfont_color="#EDEFF7", marker=dict(line=dict(color="#0A0E1A", width=2)))
        apply_theme(fig)
        fig.update_layout(height=320, showlegend=True)
        st.plotly_chart(fig, width="stretch")

    with col2:
        components.section_title("Business Risk Snapshot", "⚠️")
        risk_df = pd.DataFrame({
            "Risk": ["Declining demand", "Regime shift", "Stockout exposure", "High MOQ coverage (>90d)", "Surplus risk", "Missing financial data"],
            "Count": [ov["declining_sku_count"], ov["regime_shift_count"], ov["stockout_exposed_count"], ov["high_moq_risk_count"], ov["surplus_risk_count"], ov["missing_financial_data_count"]],
        }).sort_values("Count")
        fig2 = go.Figure(go.Bar(
            x=risk_df["Count"], y=risk_df["Risk"], orientation="h",
            marker=dict(color=risk_df["Count"], colorscale=[[0, "#4E7CF6"], [1, CRITICAL]]),
            text=risk_df["Count"], textposition="outside",
        ))
        apply_theme(fig2)
        fig2.update_layout(height=320, showlegend=False)
        st.plotly_chart(fig2, width="stretch")

    st.html("<div style='height:6px;'></div>")
    col1, col2 = st.columns(2)
    with col1:
        components.section_title("Top SKU Opportunities", "🌟")
        st.caption("Healthy margin, stable/growing demand, not overexposed on MOQ.")
        try:
            opp = post("/llm/ask", json={"question": "Which products should we prioritize?"})
            rows = (opp.get("tool_calls") or [{}])[0].get("result", {}).get("rows", [])
        except APIError:
            rows = []
        if rows:
            st.dataframe(pd.DataFrame(rows).head(8), width="stretch", hide_index=True)
        else:
            st.caption("No standout opportunities under the current filter — see Demand Profiling for the full picture.")

    with col2:
        components.section_title("Top Business Risks", "🔥")
        st.caption("Cross-module: declining demand, MOQ exposure, stockouts, missing financials.")
        try:
            risks = post("/llm/ask", json={"question": "What are the major demand and profitability risks?"})
            risk_data = (risks.get("tool_calls") or [{}])[0].get("result", {})
        except APIError:
            risk_data = {}
        declining = risk_data.get("declining_demand", [])
        if declining:
            st.dataframe(pd.DataFrame(declining).head(5), width="stretch", hide_index=True)
        else:
            st.caption("No major risks surfaced in the top-ranked list.")

    st.html("<div style='height:6px;'></div>")
    components.section_title("AI Executive Summary", "🤖")
    if st.button("Generate executive summary", type="secondary"):
        try:
            summary = post("/llm/ask", json={"question": "What are the major demand and profitability risks?"})
            st.session_state["_exec_summary"] = summary["answer"]
        except APIError as exc:
            st.error(str(exc))
    if st.session_state.get("_exec_summary"):
        components.insight_panel("Portfolio summary", st.session_state["_exec_summary"].replace("\n", "<br>"), icon="🧠")

    st.caption("Go to **Forecasting** for SKU-level forecasts, or ask the **AI Business Assistant** for deeper, free-form analysis.")
