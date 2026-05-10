"""Lumen budget and policy primitives.

These types define the bounded request surface for Lumen's chat-only core and
future lightweight tools. They intentionally do not contain recursive research
or autonomous task execution controls.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

LumenPolicy = Literal["off", "auto", "on"]
LUMEN_POLICIES: set[str] = {"off", "auto", "on"}


def _clamp_int(value: Any, *, default: int, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(min_value, min(max_value, parsed))


def _model_to_raw(value: BaseModel | dict[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, BaseModel):
        return value.model_dump() if hasattr(value, "model_dump") else value.dict()
    if isinstance(value, dict):
        return value
    return {}


def _coerce_bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off", ""}:
            return False
    return bool(value)


class LumenSearchBudget(BaseModel):
    """One-shot lightweight web-assist limits for Lumen chat jobs."""

    max_queries: int = 3
    max_results_per_query: int = 5
    max_fetch_pages: int = 3
    max_total_chars: int = 12000
    timeout_sec: int = 20


class LumenWeatherBudget(BaseModel):
    """Future no-key weather-tool limits for Lumen."""

    max_geocoding_results: int = 3
    forecast_days: int = 3
    timeout_sec: int = 10


class LumenNewsBudget(BaseModel):
    """Future no-key news-tool limits for Lumen."""

    max_providers: int = 3
    max_queries: int = 2
    max_results_per_provider: int = 5
    max_total_items: int = 15
    max_fetch_pages: int = 0
    timeout_sec: int = 20
    save_to_nexus: bool = False


def clamp_lumen_search_budget(budget: LumenSearchBudget | dict[str, Any] | None) -> LumenSearchBudget:
    raw = _model_to_raw(budget)
    return LumenSearchBudget(
        max_queries=_clamp_int(raw.get("max_queries"), default=3, min_value=0, max_value=5),
        max_results_per_query=_clamp_int(raw.get("max_results_per_query"), default=5, min_value=1, max_value=10),
        max_fetch_pages=_clamp_int(raw.get("max_fetch_pages"), default=3, min_value=0, max_value=5),
        max_total_chars=_clamp_int(raw.get("max_total_chars"), default=12000, min_value=2000, max_value=30000),
        timeout_sec=_clamp_int(raw.get("timeout_sec"), default=20, min_value=5, max_value=60),
    )


def clamp_lumen_weather_budget(budget: LumenWeatherBudget | dict[str, Any] | None) -> LumenWeatherBudget:
    raw = _model_to_raw(budget)
    return LumenWeatherBudget(
        max_geocoding_results=_clamp_int(raw.get("max_geocoding_results"), default=3, min_value=1, max_value=5),
        forecast_days=_clamp_int(raw.get("forecast_days"), default=3, min_value=1, max_value=7),
        timeout_sec=_clamp_int(raw.get("timeout_sec"), default=10, min_value=5, max_value=30),
    )


def clamp_lumen_news_budget(budget: LumenNewsBudget | dict[str, Any] | None) -> LumenNewsBudget:
    raw = _model_to_raw(budget)
    return LumenNewsBudget(
        max_providers=_clamp_int(raw.get("max_providers"), default=3, min_value=1, max_value=5),
        max_queries=_clamp_int(raw.get("max_queries"), default=2, min_value=1, max_value=5),
        max_results_per_provider=_clamp_int(raw.get("max_results_per_provider"), default=5, min_value=1, max_value=10),
        max_total_items=_clamp_int(raw.get("max_total_items"), default=15, min_value=3, max_value=30),
        max_fetch_pages=_clamp_int(raw.get("max_fetch_pages"), default=0, min_value=0, max_value=3),
        timeout_sec=_clamp_int(raw.get("timeout_sec"), default=20, min_value=5, max_value=60),
        save_to_nexus=_coerce_bool(raw.get("save_to_nexus"), default=False),
    )


def normalize_lumen_tool_policy(tool_policy: str | None) -> LumenPolicy:
    normalized = "auto" if tool_policy is None else str(tool_policy).strip().lower()
    if normalized not in LUMEN_POLICIES:
        return "auto"
    return normalized  # type: ignore[return-value]


def normalize_lumen_search_policy(search_policy: str | None) -> LumenPolicy:
    normalized = "auto" if search_policy is None else str(search_policy).strip().lower()
    if normalized not in LUMEN_POLICIES:
        return "auto"
    return normalized  # type: ignore[return-value]
