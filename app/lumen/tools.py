"""Skeleton planner for future Lumen lightweight tools.

No network calls live here. The planner records what a later weather/news/web PR
could call, while preserving chat-only execution in the current PR.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.lumen.budgets import (
    LumenNewsBudget,
    LumenSearchBudget,
    LumenWeatherBudget,
    normalize_lumen_tool_policy,
)
from app.lumen.intent import LumenIntent


class LumenToolPlan(BaseModel):
    """Non-executing plan for future Lumen tools."""

    tools: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LumenToolResult(BaseModel):
    """Placeholder result shape for future Lumen tools."""

    tool: str
    ok: bool = False
    content: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


def _budget_dump(budget: BaseModel | None) -> dict[str, Any]:
    if budget is None:
        return {}
    return budget.model_dump() if hasattr(budget, "model_dump") else budget.dict()


def plan_lumen_tools(
    *,
    intent: LumenIntent,
    tool_policy: str = "auto",
    search_policy: str = "auto",
    search_budget: LumenSearchBudget | None = None,
    weather_budget: LumenWeatherBudget | None = None,
    news_budget: LumenNewsBudget | None = None,
    location: str | None = None,
) -> LumenToolPlan:
    """Return future-tool metadata without executing any external provider."""

    normalized_tool_policy = normalize_lumen_tool_policy(tool_policy)
    metadata: dict[str, Any] = {
        "intent": intent.kind,
        "intent_reason": intent.reason,
        "tool_policy": normalized_tool_policy,
        "search_policy": search_policy,
        "executed": False,
    }
    if normalized_tool_policy == "off" or intent.kind == "chat":
        return LumenToolPlan(tools=[], metadata=metadata)
    if intent.kind == "nexus_deep_research_suggestion":
        metadata["handoff"] = "nexus_deep_research"
        metadata["message"] = "Nexus Deep Research can perform multiple searches and report generation."
        return LumenToolPlan(tools=[], metadata=metadata)

    future_tool_by_intent = {"weather": "weather", "news": "news", "web": "web"}
    tool = future_tool_by_intent.get(intent.kind)
    if tool is None:
        return LumenToolPlan(tools=[], metadata=metadata)

    metadata.update(
        {
            "planned_only": True,
            "location": location,
            "search_budget": _budget_dump(search_budget),
            "weather_budget": _budget_dump(weather_budget),
            "news_budget": _budget_dump(news_budget),
        }
    )
    return LumenToolPlan(tools=[tool], metadata=metadata)


def compress_lumen_tool_results_for_llm(results: list[LumenToolResult] | None) -> str:
    """Compress future tool results into a small text block for the LLM."""

    if not results:
        return ""
    lines = []
    for result in results:
        status = "ok" if result.ok else "error"
        lines.append(f"[{result.tool}:{status}] {result.content}".strip())
    return "\n".join(lines)
