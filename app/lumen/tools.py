"""Planner and executor for bounded Lumen lightweight tools.

Weather and lightweight news execute in Lumen. Web remains planned-only, and
Nexus Deep Research remains a handoff suggestion rather than an automatic run.
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
from app.lumen.intent import LumenIntent, extract_weather_location_hint
from app.lumen.news import LumenNewsRequest, build_nexus_news_handoff, compress_news_result_for_llm, run_lumen_news_tool
from app.lumen.weather import (
    LumenWeatherRequest,
    compress_weather_result_for_llm,
    run_lumen_weather_tool,
)


class LumenToolPlan(BaseModel):
    """Plan for bounded Lumen tools."""

    tools: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LumenToolResult(BaseModel):
    """Result shape for executed or skipped Lumen tools."""

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
    """Return tool metadata without executing any external provider."""

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
        metadata["news_budget"] = _budget_dump(news_budget)
        return LumenToolPlan(tools=[], metadata=metadata)

    future_tool_by_intent = {"weather": "weather", "news": "news", "web": "web"}
    tool = future_tool_by_intent.get(intent.kind)
    if tool is None:
        return LumenToolPlan(tools=[], metadata=metadata)

    metadata.update(
        {
            "planned_only": tool == "web",
            "executable": tool in {"weather", "news"},
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


def execute_lumen_weather_if_needed(
    *,
    intent: LumenIntent,
    tool_policy: str = "auto",
    message: str = "",
    location: str | None = None,
    weather_budget: LumenWeatherBudget | dict[str, Any] | None = None,
) -> LumenToolResult | None:
    """Execute only the weather tool when policy and intent allow it."""

    normalized_tool_policy = normalize_lumen_tool_policy(tool_policy)
    if normalized_tool_policy == "off" or intent.kind != "weather":
        return None

    resolved_location = (location or "").strip() or extract_weather_location_hint(message)
    result = run_lumen_weather_tool(
        LumenWeatherRequest(
            message=message,
            location=resolved_location,
            budget=weather_budget if isinstance(weather_budget, LumenWeatherBudget) else LumenWeatherBudget(**(weather_budget or {})),
        )
    )
    content = compress_weather_result_for_llm(result)
    metadata = result.model_dump() if hasattr(result, "model_dump") else result.dict()
    metadata["context"] = content
    metadata["location_hint"] = resolved_location
    return LumenToolResult(tool="weather", ok=result.ok, content=content, metadata=metadata)


def execute_lumen_tool_plan(
    *,
    plan: LumenToolPlan,
    intent: LumenIntent,
    tool_policy: str = "auto",
    message: str = "",
    location: str | None = None,
    weather_budget: LumenWeatherBudget | dict[str, Any] | None = None,
    news_budget: LumenNewsBudget | dict[str, Any] | None = None,
    project: str = "default",
) -> list[LumenToolResult]:
    """Execute the runnable subset of a Lumen tool plan.

    Weather and lightweight news can run. Web stays planned-only. Nexus Deep
    Research suggestions return handoff metadata only and are never auto-started.
    """

    normalized_tool_policy = normalize_lumen_tool_policy(tool_policy)
    if normalized_tool_policy == "off":
        return []

    results: list[LumenToolResult] = []
    if "weather" in plan.tools:
        weather = execute_lumen_weather_if_needed(
            intent=intent,
            tool_policy=tool_policy,
            message=message,
            location=location,
            weather_budget=weather_budget,
        )
        if weather is not None:
            results.append(weather)

    if "news" in plan.tools and intent.kind == "news":
        resolved_budget = news_budget if isinstance(news_budget, LumenNewsBudget) else LumenNewsBudget(**(news_budget or {}))
        news = run_lumen_news_tool(LumenNewsRequest(message=message, budget=resolved_budget, include_personal_use_only=True))
        content = compress_news_result_for_llm(news)
        metadata = news.model_dump() if hasattr(news, "model_dump") else news.dict()
        metadata["context"] = content
        results.append(LumenToolResult(tool="news", ok=news.ok, content=content, metadata=metadata))

    if "nexus_deep_research_suggestion" in plan.tools and intent.kind == "nexus_deep_research_suggestion":
        handoff = build_nexus_news_handoff(
            message,
            project=project,
            news_budget=(news_budget.model_dump() if isinstance(news_budget, LumenNewsBudget) and hasattr(news_budget, "model_dump") else (news_budget.dict() if isinstance(news_budget, LumenNewsBudget) else news_budget)),
        )
        results.append(
            LumenToolResult(
                tool="nexus_deep_research_suggestion",
                ok=True,
                content=handoff["message"],
                metadata={**handoff, "deep_research_started": False, "save_evidence": False},
            )
        )
    return results
