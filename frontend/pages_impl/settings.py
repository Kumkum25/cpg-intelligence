import os

import streamlit as st

import components
from api_client import APIError, BASE_URL, get


def render():
    components.page_header("Settings", "Backend connection, dataset configuration, and LLM provider status.", icon="⚙️")

    components.section_title("Backend Connection", "🔌")
    st.write(f"API base URL: `{BASE_URL}`")
    st.caption("Change via the NEXUS_API_URL environment variable before starting Streamlit.")

    try:
        health = get("/health")
    except APIError as exc:
        st.error(f"Backend unreachable: {exc}")
        return

    components.kpi_row([
        {"label": "Status", "value": health["status"].upper(), "icon": "🟢", "tone": "positive"},
        {"label": "Pipeline Loaded", "value": "Yes" if health["pipeline_loaded"] else "No", "icon": "✅" if health["pipeline_loaded"] else "⏳", "tone": "positive" if health["pipeline_loaded"] else "warning"},
        {"label": "As-of Date", "value": health["asof"], "icon": "📅", "tone": "cyan"},
    ])
    with st.expander("Raw health response"):
        st.json(health)

    components.divider_label("Dataset Configuration")
    is_sample = "nexus_cpg_sample_data_v1" in health.get("data_dir", "")
    components.dataset_pill(is_sample, health.get("data_dir", "").split("/")[-1])
    st.caption("Change the data directory or as-of date from the **Data Management** page.")

    components.divider_label("LLM Provider (AI Business Assistant)")
    provider = os.environ.get("NEXUS_LLM_PROVIDER", "mock")
    if provider == "mock":
        components.status_pill("Provider: mock (rule-based, free)", True)
        st.info(
            "Running in free, rule-based mode — no LLM API key configured, no cost. "
            "To enable real natural-language understanding, set these environment variables "
            "before starting the API server, then restart it:\n\n"
            "- `NEXUS_LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY=...` (usage-based cost), or\n"
            "- `NEXUS_LLM_PROVIDER=openai` and `OPENAI_API_KEY=...` (usage-based cost)."
        )
    else:
        key_var = "ANTHROPIC_API_KEY" if provider == "anthropic" else "OPENAI_API_KEY"
        key_present = bool(os.environ.get(key_var))
        components.status_pill(f"Provider: {provider}", key_present, "API key detected" if key_present else "key env var not detected on THIS process — the backend process is what matters")

    components.divider_label("About")
    st.caption(
        "Nexus CPG Intelligence — Demand Profiling, Economic Profiling, Forecasting, and an AI Business Assistant, "
        "all built on real nexus_engine calculations. No figure shown anywhere in this app is invented by the AI layer."
    )
