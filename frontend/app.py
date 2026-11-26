"""Nexus CPG Intelligence — Streamlit frontend.

Run with:  streamlit run frontend/app.py
(Requires the FastAPI backend running separately: uvicorn api.main:app --reload)
"""
import os
import sys

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import components  # noqa: E402
from api_client import APIError, BASE_URL, get, is_backend_up  # noqa: E402
from pages_impl import (  # noqa: E402
    assistant_page, data_management, demand, economics, forecasting, overview, reports, settings, sku_intelligence,
)

st.set_page_config(page_title="Nexus CPG Intelligence", page_icon="🧠", layout="wide", initial_sidebar_state="expanded")
components.inject_global_css()

NAV = [
    ("Overview", "📊", overview),
    ("Data Management", "🗄️", data_management),
    ("Demand Profiling", "📈", demand),
    ("Economic Profiling", "💰", economics),
    ("Forecasting", "🔮", forecasting),
    ("SKU Intelligence", "🧠", sku_intelligence),
    ("AI Business Assistant", "🤖", assistant_page),
    ("Reports and Exports", "📁", reports),
    ("Settings", "⚙️", settings),
]

if "_active_page" not in st.session_state:
    st.session_state["_active_page"] = "Overview"

with st.sidebar:
    st.html("""
    <div style="display:flex;align-items:center;gap:10px;margin:4px 0 2px 0;">
        <div style="width:38px;height:38px;border-radius:11px;
                    background:linear-gradient(135deg,#8B6CF6 0%,#4E7CF6 55%,#22D3EE 100%);
                    display:flex;align-items:center;justify-content:center;font-size:1.1rem;">🧠</div>
        <div style="line-height:1.15;">
            <div style="color:#EDEFF7;font-weight:800;font-size:1.05rem;letter-spacing:-0.01em;">Nexus CPG</div>
            <div style="color:#8B93B4;font-size:0.72rem;letter-spacing:0.03em;">INTELLIGENCE PLATFORM</div>
        </div>
    </div>
    """)
    st.html('<div style="height:14px;"></div>')

    backend_up = is_backend_up()
    components.status_pill("Backend", backend_up, BASE_URL.replace("http://", "").replace("https://", ""))

    dataset_label, dataset_detail = "No data loaded", ""
    if backend_up:
        try:
            h = get("/health")
            if h.get("pipeline_loaded"):
                is_sample = "nexus_cpg_sample_data_v1" in h.get("data_dir", "")
                dataset_label = "Sample Dataset" if is_sample else "Custom Dataset"
                dataset_detail = f"as of {h.get('asof', '')}"
            else:
                dataset_label = "Pipeline not run"
        except APIError:
            pass
    components.status_pill("Dataset", dataset_label not in ("No data loaded", "Pipeline not run"), f"{dataset_label} · {dataset_detail}" if dataset_detail else dataset_label)

    st.html('<div style="height:10px;"></div>')
    components.divider_label("Navigate")

    for name, icon, _module in NAV:
        is_active = st.session_state["_active_page"] == name
        if st.button(f"{icon}  {name}", key=f"nav_{name}", type="primary" if is_active else "secondary", width="stretch"):
            st.session_state["_active_page"] = name
            st.rerun()

    st.html('<div style="height:8px;"></div>')
    components.divider_label("About")
    st.caption("Demand · Economics · Forecasting · AI, built on real pipeline calculations — every number traces back to nexus_engine.")

page = st.session_state["_active_page"]
module = next(m for n, i, m in NAV if n == page)

if backend_up:
    module.render()
else:
    components.page_header("Backend unreachable", "Start the FastAPI server, then refresh this page.", icon="⚠️")
    st.code("cd 'cpg forecast' && source .venv/bin/activate && uvicorn api.main:app --reload --port 8000", language="bash")
