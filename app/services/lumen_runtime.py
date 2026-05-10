"""Lumen submit runtime orchestration and direct tool services.

This module owns Lumen chat job submission and background execution. HTTP
routers call into these functions, while generic job persistence remains in
``app.services.jobs`` and domain/tool logic remains in ``app.lumen``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel

from app.lumen.budgets import (
    LumenNewsBudget,
    LumenSearchBudget,
    LumenWeatherBudget,
    clamp_lumen_news_budget,
    clamp_lumen_search_budget,
    clamp_lumen_weather_budget,
    normalize_lumen_search_policy,
    normalize_lumen_tool_policy,
)
from app.lumen.intent import detect_lumen_intent
from app.lumen.news import LumenNewsRequest, run_lumen_news_tool
from app.lumen.tools import compress_lumen_tool_results_for_llm, execute_lumen_tool_plan, plan_lumen_tools
from app.lumen.weather import LumenWeatherRequest, run_lumen_weather_tool
from app.nexus.news_connectors import DEFAULT_PROVIDERS
from app.services.jobs import append_job_event, fail_job, finalize_job

LUMEN_LEGACY_MODES = {"task", "agent_task", "legacy_task"}
LUMEN_CHAT_MODES = {None, "", "chat", "lumen", "conversation"}

LUMEN_MAX_STEPS_DEFAULT = 8
LUMEN_MAX_STEPS_MIN = 1
LUMEN_MAX_STEPS_MAX = 20


def _dump_model(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    if isinstance(value, dict):
        return dict(value)
    return {}


def _clamp_int(value: Any, *, default: int, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(min_value, min(max_value, parsed))


def normalize_lumen_job_mode(mode: str | None) -> str:
    """Normalize Lumen aliases and reject removed task-like modes."""
    normalized = "" if mode is None else str(mode).strip().lower()
    if normalized in LUMEN_LEGACY_MODES:
        raise ValueError("legacy_task_mode_removed")
    if normalized in {"", "chat", "lumen", "conversation"}:
        return "chat"
    raise ValueError("invalid_lumen_mode")


def resolve_lumen_search_policy(search_enabled: bool | None, search_policy: str | None = "auto") -> str:
    if search_enabled is False:
        return "off"
    if search_enabled is True:
        return "on"
    return normalize_lumen_search_policy(search_policy)


def legacy_task_mode_removed_payload() -> dict[str, Any]:
    return {
        "ok": False,
        "error": "legacy_task_mode_removed",
        "message": "Legacy task mode has been removed. Use Lumen chat or Atlas/Agent.",
    }


def clamp_lumen_max_steps(value: Any) -> int:
    return _clamp_int(
        value,
        default=LUMEN_MAX_STEPS_DEFAULT,
        min_value=LUMEN_MAX_STEPS_MIN,
        max_value=LUMEN_MAX_STEPS_MAX,
    )


def _legacy_task_mode_exception() -> HTTPException:
    return HTTPException(status_code=410, detail=legacy_task_mode_removed_payload())


def validate_lumen_submit_request(req: Any) -> Any:
    """Validate and normalize a Lumen submit request in place."""
    try:
        req.mode = normalize_lumen_job_mode(getattr(req, "mode", None))
        req.tool_policy = normalize_lumen_tool_policy(getattr(req, "tool_policy", "auto"))
        req.search_policy = resolve_lumen_search_policy(
            getattr(req, "search_enabled", None),
            getattr(req, "search_policy", "auto"),
        )
        req.max_steps = clamp_lumen_max_steps(getattr(req, "max_steps", LUMEN_MAX_STEPS_DEFAULT))
        req.search_budget = clamp_lumen_search_budget(getattr(req, "search_budget", None) or LumenSearchBudget())
        req.weather_budget = clamp_lumen_weather_budget(getattr(req, "weather_budget", None) or LumenWeatherBudget())
        req.news_budget = clamp_lumen_news_budget(getattr(req, "news_budget", None) or LumenNewsBudget())
    except ValueError as exc:
        if str(exc) == "legacy_task_mode_removed":
            raise _legacy_task_mode_exception() from exc
        raise HTTPException(
            status_code=422,
            detail={"ok": False, "error": str(exc), "message": "Unsupported Lumen job submit option."},
        ) from exc
    return req


def build_lumen_submit_response(job_id: str, *, current_model_key: str, status: str = "queued") -> dict[str, Any]:
    return {"job_id": job_id, "status": status, "model": current_model_key}


def submit_lumen_job_service(
    req: Any,
    *,
    create_job: Callable[[str, str, str], str],
    thread_factory: Callable[..., Any],
    background_runner: Callable[[str, Any], Any],
    current_model_key: str,
) -> dict[str, Any]:
    """Create a chat-only Lumen job and start its background runner."""
    validate_lumen_submit_request(req)
    job_id = create_job(req.project, req.message, req.mode)
    thread = thread_factory(target=background_runner, args=(job_id, req), daemon=True)
    thread.start()
    return build_lumen_submit_response(job_id, current_model_key=current_model_key)


def _format_job_exception(ex: Exception) -> str:
    if isinstance(ex, HTTPException) and isinstance(ex.detail, dict):
        detail = ex.detail
        if detail.get("error") == "llm_not_ready":
            return f"LLM not ready: {detail.get('message', 'LLM server is not running.')}"
        if detail.get("error") == "web_unavailable":
            return f"Web unavailable: {detail.get('message', 'Web search provider is unavailable.')}"
        return str(detail.get("message") or detail)
    return str(ex)


LUMEN_SEARCH_EVENT_TYPES = {"web_search", "search", "web_result", "search_result", "web_context"}
LUMEN_SEARCH_ITEM_FIELDS = (
    "items",
    "results",
    "sources",
    "web_results",
    "search_results",
    "citations",
    "context_sources",
    "documents",
    "evidence",
)


def _is_lumen_search_event(ev: dict[str, Any]) -> bool:
    event_type = str(ev.get("type") or "").strip().lower()
    action = str(ev.get("action") or "").strip().lower()
    tool = str(ev.get("tool") or ev.get("name") or "").strip().lower()
    if event_type in LUMEN_SEARCH_EVENT_TYPES or action in LUMEN_SEARCH_EVENT_TYPES:
        return True
    return event_type == "tool_result" and (tool == "search" or action == "search")


def _as_event_items(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _normalize_lumen_search_item(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        normalized = dict(item)
        title = (
            normalized.get("title")
            or normalized.get("headline")
            or normalized.get("name")
            or normalized.get("display_name")
        )
        url = normalized.get("url") or normalized.get("link") or normalized.get("source_url") or normalized.get("href")
        source = (
            normalized.get("source")
            or normalized.get("provider")
            or normalized.get("domain")
            or normalized.get("site")
            or normalized.get("publisher")
        )
        snippet = (
            normalized.get("snippet")
            or normalized.get("summary")
            or normalized.get("text")
            or normalized.get("content")
            or normalized.get("description")
        )
        normalized.update(
            {"title": title or "", "url": url or "", "source": source or "", "snippet": snippet or ""}
        )
        return normalized
    text = str(item)
    return {"title": text, "url": "", "source": "", "snippet": text}


def normalize_lumen_runtime_event(ev: dict[str, Any]) -> dict[str, Any]:
    """Normalize web/search assist events to the Lumen tool_result contract."""
    if not isinstance(ev, dict) or not _is_lumen_search_event(ev):
        return ev

    raw_items: list[Any] = []
    for field in LUMEN_SEARCH_ITEM_FIELDS:
        raw_items.extend(_as_event_items(ev.get(field)))

    items = [_normalize_lumen_search_item(item) for item in raw_items]
    metadata = dict(ev.get("metadata") or {})
    ok = len(items) > 0
    metadata.update(
        {
            "overall_status": "ok" if ok else "failed",
            "provider": metadata.get("provider") or "web_assist",
            "raw_event_type": ev.get("type", "chat_step"),
            "item_count": len(items),
        }
    )
    if not ok:
        metadata["empty"] = True

    return {
        "type": "tool_result",
        "tool": "search",
        "action": "search",
        "ok": ok,
        "item_count": len(items),
        "items": items,
        "metadata": metadata,
    }


def _write_normalized_lumen_runtime_event(write: Callable[[str, dict[str, Any]], None], ev: dict[str, Any]) -> None:
    normalized = normalize_lumen_runtime_event(ev)
    write(normalized.get("type", ev.get("type", "chat_step")), normalized)


BAD_ASSISTANT_HISTORY_PATTERNS = (
    "以降、回答は必ず有効なJSON",
    "JSON形式のみで出力",
    "必ず有効なJSON形式",
)


def sanitize_lumen_chat_history(history: Any) -> list[dict[str, Any]]:
    """Keep compact Lumen history while dropping stale JSON-only assistant compliance."""

    if not isinstance(history, list):
        return []
    sanitized: list[dict[str, Any]] = []
    for item in history[-10:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "user")
        text = item.get("text", item.get("content", ""))
        text = "" if text is None else str(text)
        if role == "assistant" and any(pattern in text for pattern in BAD_ASSISTANT_HISTORY_PATTERNS):
            continue
        sanitized.append({"role": role, "text": text, "content": text})
    return sanitized[-10:]


def should_enable_lumen_web_search(intent: Any, req: Any, tool_results: Any = None) -> bool:
    """Keep Lumen lightweight tool intents from falling through to web assist."""

    if getattr(req, "search_policy", "auto") == "off":
        return False
    if getattr(intent, "kind", None) == "weather":
        return False
    if getattr(intent, "kind", None) == "news":
        return False
    if getattr(intent, "kind", None) == "web":
        return True
    return getattr(req, "search_policy", "auto") == "on"


def run_lumen_job_background_service(job_id: str, req: Any, deps: Any) -> None:
    """Run a Lumen chat job with bounded lightweight tools and chat executor."""
    validate_lumen_submit_request(req)

    project = req.project
    seq = 0
    event = deps.wait_threading.Event()
    deps.job_wait_events[job_id] = event

    def write(event_type: str, data: dict[str, Any]) -> None:
        nonlocal seq
        append_job_event(
            project=project,
            job_id=job_id,
            seq=seq,
            event_type=event_type,
            data=data,
            append_step=deps.job_append_step,
            update_status=deps.job_update_status,
            log_append=deps.job_log_append,
        )
        seq += 1

    try:
        deps.job_update_status(project, job_id, "running")
        intent = detect_lumen_intent(getattr(req, "message", ""))
        tool_plan = plan_lumen_tools(
            intent=intent,
            tool_policy=req.tool_policy,
            search_policy=req.search_policy,
            search_budget=req.search_budget,
            weather_budget=req.weather_budget,
            news_budget=req.news_budget,
            location=getattr(req, "location", None),
        )
        write("tool_plan", _dump_model(tool_plan))
        tool_results = execute_lumen_tool_plan(
            plan=tool_plan,
            intent=intent,
            tool_policy=req.tool_policy,
            message=getattr(req, "message", ""),
            location=getattr(req, "location", None),
            weather_budget=req.weather_budget,
            news_budget=req.news_budget,
            project=project,
        )
        for index, tool_result in enumerate(tool_results):
            tool_call_id = f"lumen-{tool_result.tool}-{index}"
            write(
                "tool_call",
                {
                    "id": tool_call_id,
                    "tool": tool_result.tool,
                    "action": tool_result.tool,
                    "label": f"{tool_result.tool} tool",
                    "status": "running",
                    "source": "lumen",
                },
            )
            write(
                "tool_result",
                {
                    "id": tool_call_id,
                    "tool": tool_result.tool,
                    "action": tool_result.tool,
                    "label": f"{tool_result.tool} result",
                    "ok": tool_result.ok,
                    **_dump_model(tool_result),
                    "result_preview": (tool_result.content or "")[:500],
                    "source": "lumen",
                },
            )

        tool_context = compress_lumen_tool_results_for_llm(tool_results)
        exec_url = deps.resolve_runtime_llm_url(getattr(req, "llm_url", ""))
        chat_result = deps.execute_chat_with_optional_web_search(
            req.message,
            max_steps=req.max_steps,
            search_enabled=should_enable_lumen_web_search(intent, req, tool_results),
            search_policy=req.search_policy,
            search_budget=req.search_budget,
            llm_url=exec_url,
            chat_history=sanitize_lumen_chat_history(getattr(req, "chat_history", [])),
            internal_context=tool_context,
            on_event=lambda ev: _write_normalized_lumen_runtime_event(write, ev),
        )
        chat_output = chat_result.get("output") or chat_result.get("error") or ""
        status = "done" if chat_result.get("status") == "done" else "error"
        write(
            "done",
            {
                "result": chat_output,
                "status": status,
                "usage": chat_result.get("usage", {}),
                "steps": chat_result.get("steps", []),
                "tool_policy": req.tool_policy,
                "search_policy": req.search_policy,
                "intent": _dump_model(intent),
                "tool_plan": _dump_model(tool_plan),
                "tool_results": [_dump_model(tr) for tr in tool_results],
                "search_budget": _dump_model(req.search_budget),
                "weather_budget": _dump_model(req.weather_budget),
                "news_budget": _dump_model(req.news_budget),
            },
        )
        deps.save_session(
            job_id,
            project,
            req.message,
            "chat",
            {
                "output": chat_output,
                "status": chat_result.get("status", "done"),
                "steps": chat_result.get("steps", []),
                "tool_policy": req.tool_policy,
                "search_policy": req.search_policy,
                "intent": intent.kind,
                "tool_plan": _dump_model(tool_plan),
                "tool_results": [_dump_model(tr) for tr in tool_results],
            },
        )
        if status == "done":
            finalize_job(project, job_id, deps.job_update_status)
        else:
            fail_job(project, job_id, deps.job_update_status)
    except Exception as ex:
        message = _format_job_exception(ex)
        write("error", {"error": message, "message": message})
        fail_job(project, job_id, deps.job_update_status)
    finally:
        deps.job_wait_events.pop(job_id, None)


def build_lumen_tool_status() -> dict[str, Any]:
    """Return Lumen lightweight tool availability without provider I/O."""
    return {
        "ok": True,
        "tools": {
            "weather": {"enabled": True, "provider": "open_meteo", "api_key_required": False},
            "news": {
                "enabled": True,
                "providers": list(DEFAULT_PROVIDERS),
                "api_key_required": False,
                "full_text_scraping": False,
            },
            "web": {"enabled": True, "mode": "planned_or_lightweight", "recursive_depth": 0},
        },
    }


def run_lumen_weather_direct(req: Any) -> dict[str, Any]:
    budget = clamp_lumen_weather_budget(getattr(req, "weather_budget", None) or LumenWeatherBudget())
    result = run_lumen_weather_tool(
        LumenWeatherRequest(
            message=getattr(req, "message", ""),
            location=getattr(req, "location", None),
            budget=budget,
        )
    )
    return {"ok": result.ok, "tool": "weather", "result": _dump_model(result)}


def run_lumen_news_direct(req: Any) -> dict[str, Any]:
    budget = clamp_lumen_news_budget(getattr(req, "news_budget", None) or LumenNewsBudget())
    result = run_lumen_news_tool(
        LumenNewsRequest(
            message=getattr(req, "message", ""),
            topic=getattr(req, "topic", None),
            budget=budget,
            include_personal_use_only=True,
        )
    )
    return {"ok": result.ok, "tool": "news", "result": _dump_model(result)}


__all__ = [
    "LUMEN_MAX_STEPS_DEFAULT",
    "LUMEN_MAX_STEPS_MAX",
    "LUMEN_MAX_STEPS_MIN",
    "build_lumen_submit_response",
    "build_lumen_tool_status",
    "clamp_lumen_max_steps",
    "legacy_task_mode_removed_payload",
    "normalize_lumen_job_mode",
    "resolve_lumen_search_policy",
    "run_lumen_job_background_service",
    "sanitize_lumen_chat_history",
    "should_enable_lumen_web_search",
    "run_lumen_news_direct",
    "run_lumen_weather_direct",
    "submit_lumen_job_service",
    "validate_lumen_submit_request",
]
