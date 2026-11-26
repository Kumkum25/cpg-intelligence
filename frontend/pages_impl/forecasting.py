import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import components
from api_client import APIError, get, post
from theme import ACCENT_BLUE, ACCENT_CYAN, ACCENT_PURPLE, apply_theme


def render():
    components.page_header("Forecasting Intelligence", "Multi-model demand forecasting with chronological backtesting and scenario analysis.", icon="🔮")
    try:
        skus = pd.DataFrame(get("/demand/skus"))
        models = get("/forecast/models")
    except APIError as exc:
        st.warning(f"Run the pipeline first (Data Management page). {exc}")
        return

    components.section_title("Forecast Settings", "⚙️")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        store_id = st.selectbox("Store", sorted(skus["store_id"].unique()))
    with c2:
        sku_options = sorted(skus[skus["store_id"] == store_id]["sku_code"].unique())
        sku_code = st.selectbox("SKU", sku_options)
    with c3:
        frequency = st.selectbox("Frequency", ["D", "W", "M"], format_func=lambda f: {"D": "Daily", "W": "Weekly", "M": "Monthly"}[f])
    with c4:
        horizon = st.number_input("Horizon", min_value=1, max_value=365, value=30)

    model_options = ["Auto-recommend"] + list(models.keys())
    model_choice = st.selectbox("Model", model_options, format_func=lambda k: "Auto-recommend (backtest-based)" if k == "Auto-recommend" else models[k])

    if st.button("Generate forecast", type="primary"):
        payload = {"store_id": store_id, "sku_code": sku_code, "horizon": int(horizon), "frequency": frequency}
        if model_choice != "Auto-recommend":
            payload["model"] = model_choice
        try:
            st.session_state["_forecast_result"] = post("/forecast/run", json=payload)
        except APIError as exc:
            st.error(str(exc))
            st.session_state.pop("_forecast_result", None)

    result = st.session_state.get("_forecast_result")
    if not result:
        st.info("Set your options above and click **Generate forecast**.")
        return

    if result["store_id"] != store_id or result["sku_code"] != sku_code:
        st.caption("(Showing the last generated forecast — click Generate forecast again to refresh for the current selection.)")

    components.kpi_row([
        {"label": "Selected Model", "value": result["selected_model"], "icon": "🧠", "tone": "purple"},
        {"label": "Selected By", "value": result["selected_by"].replace("_", " "), "icon": "🎯", "tone": "info"},
        {"label": "Demand Class", "value": result["demand_class"], "icon": "🏷️", "tone": "cyan"},
        {"label": "Forecast Trend", "value": result["trend"], "icon": "📈", "tone": "warning" if result["trend"] == "DECLINING" else "positive"},
    ])

    components.divider_label("Actual vs Forecast")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=result["history_dates"], y=result["history_actual"], mode="lines", name="Historical Actual", line=dict(color=ACCENT_CYAN, width=2)))
    fig.add_trace(go.Scatter(x=result["forecast_dates"], y=result["forecast_values"], mode="lines", name="Forecast", line=dict(color=ACCENT_PURPLE, width=3, dash="dash")))
    if result.get("forecast_lower") is not None:
        kind = "model-native" if result["interval_kind"] == "model_native" else "approximate (residual-based)"
        fig.add_trace(go.Scatter(x=result["forecast_dates"] + result["forecast_dates"][::-1],
                                  y=result["forecast_upper"] + result["forecast_lower"][::-1],
                                  fill="toself", fillcolor="rgba(139,108,246,0.15)", line=dict(width=0),
                                  name=f"80% interval ({kind})", showlegend=True))
    fig.add_vline(x=result["forecast_dates"][0], line_width=1, line_dash="dot", line_color="#3A4278")
    fig.update_xaxes(range=[result["history_dates"][max(0, len(result["history_dates"]) - 180)], result["forecast_dates"][-1]])
    apply_theme(fig)
    fig.update_layout(height=480, legend=dict(orientation="h", y=1.08))
    st.plotly_chart(fig, width="stretch")

    components.divider_label("Model Comparison (Chronological Walk-Forward Backtest)")
    comp_rows = []
    for c in result["comparison"]:
        m = c["metrics"] or {}
        comp_rows.append({"Model": c["model_name"], "Folds": c["folds_run"], "MAE": m.get("mae"), "RMSE": m.get("rmse"),
                           "WAPE": m.get("wape"), "MASE": m.get("mase"), "Bias": m.get("bias"),
                           "Selected": "⭐" if c["model_key"] == result["selected_model"] else ""})
    st.dataframe(pd.DataFrame(comp_rows), width="stretch", hide_index=True)

    for w in result.get("warnings", []):
        st.warning(w)
    components.insight_panel("Forecast summary", result["summary"], icon="🧠")

    with st.expander("Forecast table"):
        st.dataframe(pd.DataFrame({"date": result["forecast_dates"], "forecast": result["forecast_values"],
                                    "lower": result.get("forecast_lower"), "upper": result.get("forecast_upper")}),
                     width="stretch", hide_index=True)

    components.divider_label("Scenario Analysis: Price Change")
    st.caption("No price-elasticity effect is ever invented. Supply an assumption explicitly, or leave it blank to see the baseline forecast returned unchanged (and why).")
    c1, c2 = st.columns(2)
    with c1:
        price_change_pct = st.slider("Proposed price change (%)", -30, 30, 5) / 100
    with c2:
        use_elasticity = st.checkbox("Supply an elasticity assumption")
        elasticity = st.number_input("Assumed price elasticity of demand (e.g. -1.2)", value=-1.2, step=0.1) if use_elasticity else None

    if st.button("Run scenario", type="secondary"):
        payload = {"store_id": store_id, "sku_code": sku_code, "horizon": int(horizon), "frequency": frequency,
                   "price_change_pct": price_change_pct, "assumed_elasticity": elasticity}
        if model_choice != "Auto-recommend":
            payload["model"] = model_choice
        try:
            scen = post("/forecast/scenario", json=payload)
        except APIError as exc:
            st.error(str(exc))
        else:
            components.insight_panel("Scenario result", scen["scenario"]["note"], icon="🧪")
            if scen["scenario"]["assumed_elasticity"] is not None:
                fig2 = go.Figure()
                fig2.add_trace(go.Scatter(x=scen["baseline"]["forecast_dates"], y=scen["baseline"]["forecast_values"], name="Baseline forecast", line=dict(color=ACCENT_CYAN)))
                fig2.add_trace(go.Scatter(x=scen["baseline"]["forecast_dates"], y=scen["scenario"]["adjusted_forecast"], name=f"Scenario ({price_change_pct:+.0%} price)", line=dict(color=ACCENT_BLUE)))
                apply_theme(fig2)
                fig2.update_layout(height=350)
                st.plotly_chart(fig2, width="stretch")
