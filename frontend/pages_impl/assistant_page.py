import pandas as pd
import streamlit as st

import components
from api_client import APIError, get, post


def render():
    components.page_header("AI Business Assistant", "Ask a business question; every number comes from a real nexus_engine calculation.", icon="🤖")

    try:
        examples = get("/llm/examples")["example_questions"]
        health_resp = get("/health")
    except APIError as exc:
        st.warning(f"Backend not reachable: {exc}")
        return

    if not health_resp["pipeline_loaded"]:
        st.warning("Run the pipeline first (Data Management page) before asking questions.")
        return

    with st.expander("ℹ️ How this works / provider mode", expanded=False):
        st.markdown(
            "This assistant calls real Python calculations (demand profiling, economic profiling, forecasting) "
            "for every number it shows — it never invents a figure. Without a configured LLM API key, it runs in "
            "**rule-based mode**: it matches your question to one of the analyses below via keywords, not true "
            "language understanding. Set `NEXUS_LLM_PROVIDER=anthropic` (or `openai`) with the matching API key "
            "environment variable to get real natural-language understanding and free-form follow-ups."
        )

    components.section_title("Suggested Questions", "💡")
    cols = st.columns(2)
    for i, q in enumerate(examples):
        if cols[i % 2].button(q, key=f"ex_{i}", width="stretch"):
            st.session_state["_assistant_question"] = q

    components.divider_label("Conversation")
    if "_chat_history" not in st.session_state:
        st.session_state["_chat_history"] = []

    if not st.session_state["_chat_history"]:
        st.caption("No questions asked yet — try a suggestion above or type your own below.")

    for turn in st.session_state["_chat_history"]:
        with st.chat_message("user"):
            st.write(turn["question"])
        with st.chat_message("assistant"):
            st.write(turn["answer"])
            if turn.get("tool_calls"):
                with st.expander("Underlying analysis used"):
                    for tc in turn["tool_calls"]:
                        st.markdown(f"**Tool:** `{tc['tool']}`  args: `{tc.get('args')}`")
                        result = tc.get("result", {})
                        if isinstance(result, dict) and result.get("rows") is not None:
                            st.dataframe(pd.DataFrame(result["rows"]), width="stretch", hide_index=True)
                        else:
                            st.json(result)
            components.badge_render("LLM tool-calling" if turn["is_real_llm"] else "rule-based (no LLM key configured)", "purple" if turn["is_real_llm"] else "neutral")

    prefill = st.session_state.pop("_assistant_question", "")
    question = st.chat_input("Ask a question about demand, economics, or forecasting...") or prefill

    if question:
        with st.spinner("Thinking..."):
            try:
                resp = post("/llm/ask", json={"question": question})
            except APIError as exc:
                st.error(str(exc))
            else:
                st.session_state["_chat_history"].append({"question": question, **resp})
                st.rerun()
