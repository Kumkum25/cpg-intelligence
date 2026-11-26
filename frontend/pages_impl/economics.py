import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import components
from api_client import APIError, get
from theme import ACCENT_BLUE, ACCENT_CYAN, CRITICAL, SUCCESS, WARNING, apply_theme


def render():
    components.page_header("Economic Profiling", "Gross margin, GMROI, supplier terms, and MOQ/shelf-life risk per SKU × store.", icon="💰")
    try:
        econ = pd.DataFrame(get("/economics/profile"))
    except APIError as exc:
        st.warning(f"Run the pipeline first (Data Management page). {exc}")
        return
    supplier = pd.DataFrame(get("/economics/suppliers"))

    components.section_title("Filters", "🔎")
    c1, c2 = st.columns(2)
    with c1:
        store_filter = st.selectbox("Store", ["All"] + sorted(econ["store_id"].unique()))
    with c2:
        sku_filter = st.selectbox("SKU", ["All"] + sorted(econ["sku_code"].unique()))

    view = econ.copy()
    if store_filter != "All":
        view = view[view["store_id"] == store_filter]
    if sku_filter != "All":
        view = view[view["sku_code"] == sku_filter]

    valid_gm = view[view["gm_per_ea"].notna()]
    valid_gmroi = view[view["gmroi"].notna()]
    missing = view[view["gm_issue"].notna() | view["gmroi_issue"].notna()]
    sup_view = (supplier if sku_filter == "All" else supplier[supplier["sku_code"] == sku_filter]).copy()
    sup_view["moq_investment"] = (sup_view["moq_ea"] * sup_view["unit_purchase_cost_per_ea"]).round(2)

    components.kpi_row([
        {"label": "Total Daily Gross Profit", "value": f"${valid_gm['daily_gross_profit'].sum():,.0f}", "icon": "💵", "tone": "positive"},
        {"label": "Avg Gross Margin %", "value": f"{valid_gm['gm_pct'].mean():.1%}" if not valid_gm.empty else "—", "icon": "📐", "tone": "cyan"},
        {"label": "Avg GMROI", "value": f"{valid_gmroi['gmroi'].mean():.1f}x" if not valid_gmroi.empty else "—", "icon": "🔁", "tone": "info"},
        {"label": "Total MOQ Investment", "value": f"${sup_view['moq_investment'].sum():,.0f}", "icon": "📦", "tone": "purple"},
        {"label": "Missing Financial Data", "value": len(missing), "icon": "⚠️", "tone": "warning" if len(missing) else "positive"},
    ])

    components.divider_label("Gross Margin & Gross Profit")
    show_cols = ["store_id", "sku_code", "net_price_per_ea", "cogs_per_ea", "gm_per_ea", "gm_pct",
                 "velocity_90d", "daily_gross_profit", "gmroi", "gm_issue", "gmroi_issue", "pricing_issue", "price_history_has_overlap"]
    st.dataframe(view[show_cols], width="stretch", hide_index=True)

    if not valid_gm.empty:
        top = valid_gm.sort_values("daily_gross_profit", ascending=False).head(15)
        fig = go.Figure()
        for i, store in enumerate(top["store_id"].unique()):
            d = top[top["store_id"] == store]
            fig.add_trace(go.Bar(x=d["sku_code"], y=d["daily_gross_profit"], name=store, marker_color=[ACCENT_CYAN, ACCENT_BLUE][i % 2]))
        apply_theme(fig)
        fig.update_layout(height=360, barmode="group", title="Estimated Daily Gross Profit by SKU (top 15)")
        st.plotly_chart(fig, width="stretch")

    col1, col2 = st.columns(2)
    with col1:
        components.section_title("GMROI by SKU", "🔁")
        if not valid_gmroi.empty:
            fig = go.Figure()
            for i, store in enumerate(valid_gmroi["store_id"].unique()):
                d = valid_gmroi[valid_gmroi["store_id"] == store].sort_values("gmroi", ascending=False)
                fig.add_trace(go.Bar(x=d["sku_code"], y=d["gmroi"], name=store, marker_color=[ACCENT_CYAN, ACCENT_BLUE][i % 2]))
            apply_theme(fig)
            fig.update_layout(height=320, barmode="group")
            st.plotly_chart(fig, width="stretch")
        missing_gmroi = view[view["gmroi"].isna()]
        if not missing_gmroi.empty:
            components.insight_panel(
                "GMROI not computable for some series",
                ", ".join(f"<b>{r.sku_code}</b>@{r.store_id} ({r.gmroi_issue})" for r in missing_gmroi.itertuples()),
                icon="⚠️",
            )
    with col2:
        components.section_title("Risk Indicators", "🚦")
        high_moq = sup_view[sup_view["moq_coverage_days"] > 90]
        surplus = sup_view[sup_view["surplus_risk"] == True]  # noqa: E712
        components.kpi_row([
            {"label": "High MOQ Coverage (>90d)", "value": len(high_moq), "icon": "📦", "tone": "warning" if len(high_moq) else "positive"},
            {"label": "Surplus / Shelf-Life Risk", "value": len(surplus), "icon": "⏳", "tone": "critical" if len(surplus) else "positive"},
        ])
        if not high_moq.empty:
            st.dataframe(high_moq[["sku_code", "supplier_id", "moq_coverage_days"]], width="stretch", hide_index=True)
        if not surplus.empty:
            st.dataframe(surplus[["sku_code", "supplier_id", "moq_coverage_days", "shelf_life_days"]], width="stretch", hide_index=True)

    components.divider_label("Supplier Comparison, MOQ Coverage & Shelf-Life Risk")
    st.dataframe(
        sup_view[["sku_code", "supplier_id", "ship_to_location_id", "moq_qty", "moq_uom", "moq_ea", "moq_investment",
                  "unit_purchase_cost_per_ea", "lead_time_days", "shelf_life_days", "moq_coverage_days", "surplus_risk"]],
        width="stretch", hide_index=True,
    )

    if not missing.empty:
        components.divider_label("Missing Financial Data")
        st.dataframe(missing[["store_id", "sku_code", "gm_issue", "gmroi_issue"]], width="stretch", hide_index=True)
