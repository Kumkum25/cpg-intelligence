"""Pluggable LLM providers. The provider's only job is: given a question
and the tool catalog, decide which tool(s) to call and phrase the final
answer. It is never allowed to produce a number on its own — every figure
in ``tool_results`` came from nexus_engine via tools.py.

Configure with env vars:
    NEXUS_LLM_PROVIDER = "anthropic" | "openai" | "mock"   (default: mock)
    ANTHROPIC_API_KEY   (if provider = anthropic)
    OPENAI_API_KEY       (if provider = openai)

No key configured -> MockProvider, a deterministic keyword router. It costs
nothing and needs no setup, but it's pattern-matching, not reasoning — it
only recognizes question shapes close to the examples it knows. Point
NEXUS_LLM_PROVIDER at a real provider for actual natural-language
understanding, hypothesis generation, and free-form follow-ups.
"""
from __future__ import annotations

import os
import re

from .tools import TOOLS, TOOLS_BY_NAME


class LLMProvider:
    name = "base"
    is_real_llm = False

    def answer(self, question: str, state, context: dict | None = None) -> dict:
        raise NotImplementedError


class MockProvider(LLMProvider):
    """Free, local, zero-setup fallback. Keyword/regex routing to exactly
    one (occasionally two) tools, then a templated explanation over the
    real tool output. This is intentionally simple — it is not an LLM and
    does not pretend to be one.
    """
    name = "mock_rule_based"
    is_real_llm = False

    _PATTERNS = [
        (re.compile(r"insufficient|not enough (history|data)|too little (history|data)"), "insufficient_data_skus"),
        (re.compile(r"why.*(model|select|recommend|chosen|pick)"), "why_model_selected"),
        (re.compile(r"best.*overall|overall.*model|model.*overall"), "best_overall_model"),
        (re.compile(r"all (products|skus)|every product|entire store"), "forecast_for_store"),
        (re.compile(r"intermittent|regime.?shift|pattern.*(chang|shift)"), "becoming_intermittent"),
        (re.compile(r"unusual|erratic|lumpy"), "unusual_demand_patterns"),
        (re.compile(r"increas"), "increasing_demand_skus"),
        (re.compile(r"declin"), "declining_demand"),
        (re.compile(r"stockout|out.of.stock|oos\b"), "stockout_exposure"),
        (re.compile(r"gross profit|most profitable|highest.*profit"), "highest_gross_profit"),
        (re.compile(r"high.?margin.*declin|declin.*margin"), "high_margin_declining"),
        (re.compile(r"moq.*(coverage|90|days)|coverage.*moq"), "moq_coverage_over"),
        (re.compile(r"slow.?mov|high moq"), "slow_moving_high_moq"),
        (re.compile(r"supplier.*unfavo|unfavo.*supplier|compare.*supplier"), "unfavorable_supplier_terms"),
        (re.compile(r"high moq.*forecast|low forecast.*moq|moq.*low.*demand"), "high_moq_low_forecast"),
        (re.compile(r"best.*model|which model|model.*perform"), "best_model_for_sku"),
        (re.compile(r"forecast"), "forecast_for_sku"),
        (re.compile(r"prioriti[sz]e|should we focus"), "priority_products"),
        (re.compile(r"risk"), "major_risks"),
    ]

    def _extract_entities(self, question: str, state) -> dict:
        store_match = re.search(r"STORE-\d+", question.upper())
        sku_codes = set(state.tables["demand_profile"]["sku_code"].unique()) if state.loaded else set()
        sku_match = next((s for s in sku_codes if s in question.upper()), None)
        return {"store_id": store_match.group(0) if store_match else None, "sku_code": sku_match}

    def answer(self, question: str, state, context: dict | None = None) -> dict:
        context = context or {}
        tool_name = next((name for pattern, name in self._PATTERNS if pattern.search(question.lower())), None)

        if tool_name is None:
            return {
                "answer": (
                    "I couldn't match this question to one of the analyses I can run in rule-based mode. "
                    "Try one of the example questions, or configure a real LLM provider (NEXUS_LLM_PROVIDER=anthropic/openai) "
                    "for free-form understanding."
                ),
                "tool_calls": [], "provider": self.name,
            }

        entities = self._extract_entities(question, state)
        tool = TOOLS_BY_NAME[tool_name]
        kwargs = {}
        if "store_id" in tool["parameters"] and entities.get("store_id"):
            kwargs["store_id"] = entities["store_id"]
        if "sku_code" in tool["parameters"]:
            sku = context.get("sku_code") or entities.get("sku_code")
            if tool["parameters"]["sku_code"].get("required") and not sku:
                return {"answer": f"'{tool_name}' needs a specific SKU — mention its code (e.g. WTR-500ML) in the question.", "tool_calls": [], "provider": self.name}
            if sku:
                kwargs["sku_code"] = sku
        if "store_id" in tool["parameters"] and tool["parameters"]["store_id"].get("required") and "store_id" not in kwargs:
            kwargs["store_id"] = context.get("store_id") or (state.raw.location["store_id"].iloc[0] if state.loaded else None)

        try:
            result = tool["fn"](state, **kwargs)
        except Exception as exc:
            return {"answer": f"Ran '{tool_name}' but it failed: {exc}", "tool_calls": [{"tool": tool_name, "args": kwargs, "error": str(exc)}], "provider": self.name}

        text = self._render(tool_name, result)
        return {"answer": text, "tool_calls": [{"tool": tool_name, "args": kwargs, "result": result}], "provider": self.name}

    def _render(self, tool_name: str, result: dict) -> str:
        rows = result.get("rows")
        if rows is not None:
            if not rows:
                return f"No results for '{tool_name}' — nothing matched this filter in the current data."
            lines = [f"Ran `{tool_name}` ({result.get('note', '')})", ""]
            for r in rows[:10]:
                lines.append(" - " + ", ".join(f"{k}={v}" for k, v in r.items()))
            return "\n".join(lines)
        if "summary" in result:
            return result["summary"]
        return f"Ran `{tool_name}`:\n{result}"


class _ToolCallingProviderBase(LLMProvider):
    """Shared tool-catalog -> JSON-schema conversion for the real providers."""

    def _json_schema_tools(self) -> list[dict]:
        schemas = []
        for t in TOOLS:
            props, required = {}, []
            for pname, pspec in t["parameters"].items():
                props[pname] = {"type": pspec["type"]}
                if pspec.get("required"):
                    required.append(pname)
            schemas.append({"name": t["name"], "description": t["description"],
                             "input_schema": {"type": "object", "properties": props, "required": required}})
        return schemas

    def _system_prompt(self) -> str:
        return (
            "You are the Nexus CPG Intelligence assistant. You answer questions about demand profiling, "
            "economic profiling, and forecasting for a CPG retailer, using ONLY the provided tools for any number. "
            "Never state a numeric result, metric, or forecast value that did not come from a tool call — if you "
            "don't have a tool for something, say so plainly instead of estimating. After calling tools, explain "
            "the result in plain business language and suggest a concrete next step when relevant."
        )


class AnthropicProvider(_ToolCallingProviderBase):
    name = "anthropic"
    is_real_llm = True

    def __init__(self, model: str = "claude-sonnet-5", api_key: str | None = None):
        import anthropic
        self.client = anthropic.Anthropic(api_key=api_key or os.environ["ANTHROPIC_API_KEY"])
        self.model = model

    def answer(self, question: str, state, context: dict | None = None) -> dict:
        tools = self._json_schema_tools()
        messages = [{"role": "user", "content": question}]
        tool_calls = []

        for _ in range(4):
            resp = self.client.messages.create(
                model=self.model, max_tokens=1024, system=self._system_prompt(),
                tools=tools, messages=messages,
            )
            messages.append({"role": "assistant", "content": resp.content})
            tool_uses = [b for b in resp.content if b.type == "tool_use"]
            if not tool_uses:
                text = "".join(b.text for b in resp.content if b.type == "text")
                return {"answer": text, "tool_calls": tool_calls, "provider": self.name}

            tool_results = []
            for call in tool_uses:
                fn = TOOLS_BY_NAME[call.name]["fn"]
                try:
                    result = fn(state, **call.input)
                except Exception as exc:
                    result = {"error": str(exc)}
                tool_calls.append({"tool": call.name, "args": call.input, "result": result})
                tool_results.append({"type": "tool_result", "tool_use_id": call.id, "content": str(result)})
            messages.append({"role": "user", "content": tool_results})

        return {"answer": "Reached the tool-call limit without a final answer.", "tool_calls": tool_calls, "provider": self.name}


class OpenAIProvider(_ToolCallingProviderBase):
    name = "openai"
    is_real_llm = True

    def __init__(self, model: str = "gpt-4o-mini", api_key: str | None = None):
        import openai
        self.client = openai.OpenAI(api_key=api_key or os.environ["OPENAI_API_KEY"])
        self.model = model

    def _openai_tools(self) -> list[dict]:
        return [{"type": "function", "function": {"name": s["name"], "description": s["description"], "parameters": s["input_schema"]}} for s in self._json_schema_tools()]

    def answer(self, question: str, state, context: dict | None = None) -> dict:
        import json
        messages = [{"role": "system", "content": self._system_prompt()}, {"role": "user", "content": question}]
        tool_calls = []

        for _ in range(4):
            resp = self.client.chat.completions.create(model=self.model, messages=messages, tools=self._openai_tools())
            msg = resp.choices[0].message
            messages.append(msg)
            if not msg.tool_calls:
                return {"answer": msg.content, "tool_calls": tool_calls, "provider": self.name}

            for call in msg.tool_calls:
                args = json.loads(call.function.arguments or "{}")
                fn = TOOLS_BY_NAME[call.function.name]["fn"]
                try:
                    result = fn(state, **args)
                except Exception as exc:
                    result = {"error": str(exc)}
                tool_calls.append({"tool": call.function.name, "args": args, "result": result})
                messages.append({"role": "tool", "tool_call_id": call.id, "content": str(result)})

        return {"answer": "Reached the tool-call limit without a final answer.", "tool_calls": tool_calls, "provider": self.name}


def get_provider() -> LLMProvider:
    choice = os.environ.get("NEXUS_LLM_PROVIDER", "mock").lower()
    if choice == "anthropic" and os.environ.get("ANTHROPIC_API_KEY"):
        return AnthropicProvider()
    if choice == "openai" and os.environ.get("OPENAI_API_KEY"):
        return OpenAIProvider()
    return MockProvider()
