import pandas as pd
import streamlit as st

import components
from api_client import APIError, get, post


def render():
    components.page_header("Data Management", "Inspect the active data source, run quality checks, and reprocess the pipeline.", icon="🗄️")

    try:
        health = get("/health")
    except APIError as exc:
        st.error(f"Backend unreachable: {exc}")
        return

    is_sample = "nexus_cpg_sample_data_v1" in health.get("data_dir", "")
    components.kpi_row([
        {"label": "Active Source", "value": "Sample Dataset" if is_sample else "Custom Dataset", "icon": "🧪" if is_sample else "📦", "tone": "info"},
        {"label": "Pipeline Loaded", "value": "Yes" if health["pipeline_loaded"] else "No", "icon": "✅" if health["pipeline_loaded"] else "⏳", "tone": "positive" if health["pipeline_loaded"] else "warning"},
        {"label": "As-of Date", "value": health["asof"], "icon": "📅", "tone": "cyan"},
    ])
    st.caption(f"Directory: `{health['data_dir']}`")
    if health.get("last_error"):
        st.error(f"Last pipeline error: {health['last_error']}")

    st.html("<div style='height:6px;'></div>")
    components.divider_label("Data Quality Check")
    status_target = st.radio("Check which data directory?", ["Currently configured dataset", "Uploaded files"], horizontal=True, label_visibility="collapsed")
    if st.button("Run data quality check", type="secondary"):
        try:
            status = get("/data/status") if status_target == "Currently configured dataset" else get("/data/uploaded-status")
        except APIError as exc:
            st.error(str(exc))
        else:
            st.session_state["_last_quality_report"] = status

    report = st.session_state.get("_last_quality_report")
    if report:
        ok = report["all_required_files_ok"]
        components.status_pill("All required files present & valid", ok)
        for f in report["files"]:
            icon = "✅" if f["present"] and not f.get("missing_required_columns") else "⚠️"
            with st.expander(f"{icon}  {f['file']}"):
                if not f["present"]:
                    st.error("File not found.")
                    continue
                st.write(f"Rows: {f.get('rows')}")
                if f.get("missing_required_columns"):
                    st.error(f"Missing required columns: {f['missing_required_columns']}")
                if f.get("duplicate_rows"):
                    st.warning(f"{f['duplicate_rows']} fully duplicate rows")
                null_counts = f.get("null_counts") or {}
                if null_counts:
                    st.write("Null counts by column:")
                    st.dataframe(pd.DataFrame({"column": list(null_counts.keys()), "nulls": list(null_counts.values())}), width="stretch", hide_index=True)
                if not f.get("issues"):
                    st.write("No issues detected.")

    st.html("<div style='height:6px;'></div>")
    components.divider_label("Upload Replacement Data (optional)")
    st.caption("Upload a corrected CSV for any of the 9 raw files. Uploads are saved separately from the bundled sample data and its answer key, which are never modified.")
    dataset_names = [
        "pos_sales_transactions.csv", "product_master.csv", "location_master.csv",
        "ranging.csv", "store_calendar_feed_log.csv", "inventory_daily.csv",
        "sku_economics.csv", "supplier_constraints.csv", "inventory_valuation_weekly.csv",
    ]
    c1, c2 = st.columns([1, 2])
    with c1:
        dataset_name = st.selectbox("Which file is this?", dataset_names)
    with c2:
        uploaded = st.file_uploader("Choose a CSV file", type=["csv"], label_visibility="collapsed")
    if uploaded is not None and st.button("Upload", type="secondary"):
        import requests

        from api_client import BASE_URL
        try:
            resp = requests.post(
                f"{BASE_URL}/data/upload",
                files={"file": (dataset_name, uploaded.getvalue(), "text/csv")},
                data={"dataset_name": dataset_name},
                timeout=60,
            )
            resp.raise_for_status()
            st.success("Uploaded.")
            st.json(resp.json()["quality_report"])
        except Exception as exc:
            st.error(f"Upload failed: {exc}")

    st.html("<div style='height:6px;'></div>")
    components.divider_label("Run the Profiling Pipeline")
    col1, col2 = st.columns(2)
    with col1:
        data_dir_choice = st.text_input("Data directory to run on (leave blank to keep current)", value="")
    with col2:
        asof_choice = st.text_input("As-of date (YYYY-MM-DD, leave blank to keep current)", value="")

    if st.button("Run pipeline now", type="primary"):
        try:
            result = post("/data/pipeline/run", json={"data_dir": data_dir_choice or None, "asof": asof_choice or None})
        except APIError as exc:
            st.error(f"Pipeline run failed: {exc}")
        else:
            st.success(f"Pipeline ran successfully as of {result['asof']} on {result['data_dir']}")
            st.json(result["row_counts"])
