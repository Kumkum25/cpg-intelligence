import streamlit as st

import components
from api_client import APIError, BASE_URL, get, get_raw, post
from pdf_report import build_executive_summary_pdf

TABLE_LABELS = {
    "demand_profile": ("Demand Report", "SKU x Store, 90D & 365D classification, trend, seasonality"),
    "economic_profile": ("Economic Report", "Gross margin, GMROI, pricing issues"),
    "supplier_profile": ("Supplier Risk Report", "MOQ, coverage, shelf-life / surplus risk"),
    "daily_demand": ("Daily Demand", "Cleaned, deduplicated daily sales"),
    "daily_returns": ("Daily Returns", "Deduplicated daily returns"),
    "daily_panel": ("Full Daily Panel", "Every store x SKU x date, with validity/status detail"),
}


def render():
    components.page_header("Reports and Exports", "Download analysis-ready tables, or generate an executive summary.", icon="📁")

    try:
        tables = get("/reports/tables")["exportable_tables"]
    except APIError as exc:
        st.warning(f"Run the pipeline first (Data Management page). {exc}")
        return

    st.caption(f"Backend: `{BASE_URL}`")
    components.divider_label("Data Reports (CSV / Excel)")
    for t in tables:
        label, desc = TABLE_LABELS.get(t, (t, ""))
        c1, c2, c3 = st.columns([3, 1, 1])
        with c1:
            st.markdown(f"**{label}**")
            st.caption(desc)
        try:
            csv_bytes = get_raw(f"/reports/export/{t}", params={"format": "csv"}).content
            c2.download_button("⬇ CSV", csv_bytes, file_name=f"{t}.csv", mime="text/csv", key=f"csv_{t}", width="stretch")
        except APIError:
            c2.write("—")
        try:
            xlsx_bytes = get_raw(f"/reports/export/{t}", params={"format": "xlsx"}).content
            c3.download_button("⬇ Excel", xlsx_bytes, file_name=f"{t}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f"xlsx_{t}", width="stretch")
        except APIError:
            c3.write("—")

    components.divider_label("Executive Summary (AI + PDF)")
    st.caption("Generates a narrative risk summary from the assistant's major-risks analysis, using the same underlying numbers as the Overview page.")
    if st.button("Generate executive summary", type="primary"):
        try:
            overview = get("/overview")
            resp = post("/llm/ask", json={"question": "What are the major demand and profitability risks?"})
        except APIError as exc:
            st.error(str(exc))
        else:
            st.session_state["_report_overview"] = overview
            st.session_state["_report_summary"] = resp["answer"]

    if st.session_state.get("_report_summary"):
        components.insight_panel("Executive summary", st.session_state["_report_summary"].replace("\n", "<br>"), icon="🧠")
        pdf_bytes = build_executive_summary_pdf(st.session_state["_report_overview"], st.session_state["_report_summary"])
        st.download_button("⬇ Download as PDF", pdf_bytes, file_name="nexus_executive_summary.pdf", mime="application/pdf", type="secondary")
