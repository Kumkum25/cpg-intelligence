"""The AI Business Assistant: a pluggable LLM layer (see providers.py) that
answers business questions by calling real nexus_engine calculations
(tools.py) and explaining the results — never inventing numbers itself.
"""
from .providers import get_provider
from .tools import TOOLS

EXAMPLE_QUESTIONS = [
    "Which SKUs have declining demand?",
    "Which products are becoming intermittent?",
    "Which products have unusual demand patterns?",
    "Which SKUs have the highest stockout exposure?",
    "Which products generate the highest gross profit?",
    "Which slow-moving products have high MOQ?",
    "Which products have MOQ coverage greater than 90 days?",
    "Which suppliers have unfavourable MOQ conditions?",
    "Which high-margin products are experiencing declining demand?",
    "Which model performs best for WTR-500ML at STORE-101?",
    "Why was this model selected for WTR-500ML?",
    "Which SKUs have insufficient historical data?",
    "Which forecasting model performs best overall?",
    "Which products are expected to experience increased demand?",
    "Forecast demand for WTR-500ML at STORE-101 for the next 30 days.",
    "Show me the forecast for all products in STORE-101.",
    "Which high-margin products have declining demand?",
    "Which products should we prioritize?",
    "What are the major demand and profitability risks?",
]


def answer_question(question: str, state, context: dict | None = None) -> dict:
    provider = get_provider()
    result = provider.answer(question, state, context)
    result.setdefault("provider", provider.name)
    result["is_real_llm"] = provider.is_real_llm
    return result


__all__ = ["answer_question", "get_provider", "TOOLS", "EXAMPLE_QUESTIONS"]
