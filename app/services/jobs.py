"""Job submission and execution services.

This module keeps job runtime orchestration out of ``main.py`` without owning
HTTP routes. Lumen jobs are intentionally chat-only: legacy task execution,
model orchestration, retry plans, shell/file edits, and JSON option fallback
belong to Atlas/Agent or Nexus, not this service.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import HTTPException

from app.api.jobs import (
    LUMEN_MAX_STEPS_DEFAULT,
    LUMEN_MAX_STEPS_MAX,
    LUMEN_MAX_STEPS_MIN,
    clamp_lumen_max_steps,
    legacy_task_mode_removed_payload,
    normalize_lumen_job_mode,
    resolve_lumen_search_policy,
)
from app.lumen.budgets import (
    LumenNewsBudget,
    LumenSearchBudget,
    LumenWeatherBudget,
    clamp_lumen_news_budget,
    clamp_lumen_search_budget,
    clamp_lumen_weather_budget,
    normalize_lumen_tool_policy,
)
from app.lumen.intent import detect_lumen_intent
from app.lumen.tools import compress_lumen_tool_results_for_llm, execute_lumen_tool_plan, plan_lumen_tools


def append_job_event(
    *,
    project: str,
    job_id: str,
    seq: int,
    event_type: str,
    data: dict[str, Any],
    append_step: Callable[[str, str, int, str, dict[str, Any]], Any],
    update_status: Callable[[str, str, str], Any],
    log_append: Callable[[str, dict[str, Any]], Any],
) -> None:
    """Persist a job event and mirror the existing per-job log entry shape."""
    append_step(project, job_id, seq, event_type, data)
    if event_type == "clarify":
        update_status(project, job_id, "waiting_input")

    log_entry: dict[str, Any] = {"type": event_type, "seq": seq}
    if event_type == "tool_call":
        log_entry.update(
            {
                "action": data.get("action", ""),
                "thought": data.get("thought", ""),
                "step_num": data.get("step_num"),
            }
        )
    elif event_type == "tool_result":
        log_entry["result_preview"] = data.get("result_preview", "")
    elif event_type in ("task_done", "task_error", "task_start"):
        log_entry.update(
            {
                "task_id": data.get("task_id"),
                "title": data.get("title", ""),
                "error": data.get("error", ""),
            }
        )
    elif event_type == "skill_hint":
        log_entry.update(
            {
                "missing_tool": data.get("missing_tool", ""),
                "thought": data.get("thought", ""),
            }
        )
    log_append(job_id, log_entry)


def finalize_job(project: str, job_id: str, update_status: Callable[[str, str, str], Any]) -> None:
    """Mark a job as done using the injected job status writer."""
    update_status(project, job_id, "done")


def fail_job(project: str, job_id: str, update_status: Callable[[str, str, str], Any]) -> None:
    """Mark a job as failed using the injected job status writer."""
    update_status(project, job_id, "error")


def _legacy_task_mode_exception() -> HTTPException:
    return HTTPException(status_code=410, detail=legacy_task_mode_removed_payload())


def submit_job_service(
    req: Any,
    *,
    create_job: Callable[[str, str, str], str],
    thread_factory: Callable[..., Any],
    background_runner: Callable[[str, Any], Any],
    current_model_key: str,
) -> dict[str, Any]:
    """Create a chat-only Lumen job and start the background runner.

    Legacy task-like modes are rejected before job creation so stale UI payloads
    cannot enqueue a job or start a background thread.
    """
    try:
        normalized_mode = normalize_lumen_job_mode(getattr(req, "mode", None))
    except ValueError as exc:
        if str(exc) == "legacy_task_mode_removed":
            raise _legacy_task_mode_exception() from exc
        raise HTTPException(
            status_code=422,
            detail={"ok": False, "error": str(exc), "message": "Unsupported Lumen job mode."},
        ) from exc

    req.mode = normalized_mode
    job_id = create_job(req.project, req.message, normalized_mode)
    thread = thread_factory(target=background_runner, args=(job_id, req), daemon=True)
    thread.start()
    return {
        "job_id": job_id,
        "status": "queued",
        "model": current_model_key,
    }


def _format_job_exception(ex: Exception) -> str:
    if isinstance(ex, HTTPException) and isinstance(ex.detail, dict):
        detail = ex.detail
        if detail.get("error") == "llm_not_ready":
            return f"LLM not ready: {detail.get('message', 'LLM server is not running.')}"
        if detail.get("error") == "web_unavailable":
            return f"Web unavailable: {detail.get('message', 'Web search provider is unavailable.')}"
        return str(detail.get("message") or detail)
    return str(ex)


def run_job_background_service(job_id: str, req: Any, deps: Any) -> None:
    """Run a Lumen job in the background.

    The execution path is chat-only and delegates response generation to
    ``execute_chat_with_optional_web_search``. Lumen never executes legacy task
    plans, approved task lists, shell commands, file edits, recursive research,
    or Deep Research jobs.
    """

    normalized_mode = normalize_lumen_job_mode(getattr(req, "mode", None))
    req.mode = normalized_mode

    project = req.project
    seq = 0
    job_append_step = deps.job_append_step
    job_update_status = deps.job_update_status
    job_log_append = deps.job_log_append
    execute_chat_with_optional_web_search = deps.execute_chat_with_optional_web_search
    save_session = deps.save_session
    resolve_runtime_llm_url = deps.resolve_runtime_llm_url
    wait_threading = deps.wait_threading
    job_wait_events = deps.job_wait_events

    event = wait_threading.Event()
    job_wait_events[job_id] = event

    def write(event_type: str, data: dict[str, Any]) -> None:
        nonlocal seq
        append_job_event(
            project=project,
            job_id=job_id,
            seq=seq,
            event_type=event_type,
            data=data,
            append_step=job_append_step,
            update_status=job_update_status,
            log_append=job_log_append,
        )
        seq += 1

    try:
        job_update_status(project, job_id, "running")

        clamped_max_steps = clamp_lumen_max_steps(getattr(req, "max_steps", LUMEN_MAX_STEPS_DEFAULT))
        search_policy = resolve_lumen_search_policy(
            getattr(req, "search_enabled", None),
            getattr(req, "search_policy", "auto"),
        )
        tool_policy = normalize_lumen_tool_policy(getattr(req, "tool_policy", "auto"))
        clamped_budget = clamp_lumen_search_budget(
            getattr(req, "search_budget", None) or LumenSearchBudget()
        )
        weather_budget = clamp_lumen_weather_budget(
            getattr(req, "weather_budget", None) or LumenWeatherBudget()
        )
        news_budget = clamp_lumen_news_budget(
            getattr(req, "news_budget", None) or LumenNewsBudget()
        )
        intent = detect_lumen_intent(getattr(req, "message", ""))
        tool_plan = plan_lumen_tools(
            intent=intent,
            tool_policy=tool_policy,
            search_policy=search_policy,
            search_budget=clamped_budget,
            weather_budget=weather_budget,
            news_budget=news_budget,
            location=getattr(req, "location", None),
        )
        write(
            "tool_plan",
            tool_plan.model_dump() if hasattr(tool_plan, "model_dump") else tool_plan.dict(),
        )
        tool_results = execute_lumen_tool_plan(
            plan=tool_plan,
            intent=intent,
            tool_policy=tool_policy,
            message=getattr(req, "message", ""),
            location=getattr(req, "location", None),
            weather_budget=weather_budget,
            news_budget=news_budget,
            project=project,
        )
        for tool_result in tool_results:
            result_payload = tool_result.model_dump() if hasattr(tool_result, "model_dump") else tool_result.dict()
            write(
                "tool_result",
                {
                    **result_payload,
                    "result_preview": (tool_result.content or "")[:500],
                },
            )
        tool_context = compress_lumen_tool_results_for_llm(tool_results)
        effective_search_enabled = search_policy != "off"
        exec_url = resolve_runtime_llm_url(getattr(req, "llm_url", ""))

        chat_result = execute_chat_with_optional_web_search(
            req.message,
            max_steps=clamped_max_steps,
            search_enabled=effective_search_enabled,
            search_policy=search_policy,
            search_budget=clamped_budget,
            llm_url=exec_url,
            chat_history=getattr(req, "chat_history", []),
            internal_context=tool_context,
            on_event=lambda ev: write(ev.get("type", "chat_step"), ev),
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
                "tool_policy": tool_policy,
                "search_policy": search_policy,
                "intent": intent.model_dump() if hasattr(intent, "model_dump") else intent.dict(),
                "tool_plan": tool_plan.model_dump() if hasattr(tool_plan, "model_dump") else tool_plan.dict(),
                "tool_results": [tr.model_dump() if hasattr(tr, "model_dump") else tr.dict() for tr in tool_results],
                "search_budget": clamped_budget.model_dump()
                if hasattr(clamped_budget, "model_dump")
                else clamped_budget.dict(),
                "weather_budget": weather_budget.model_dump()
                if hasattr(weather_budget, "model_dump")
                else weather_budget.dict(),
                "news_budget": news_budget.model_dump()
                if hasattr(news_budget, "model_dump")
                else news_budget.dict(),
            },
        )
        save_session(
            job_id,
            project,
            req.message,
            "chat",
            {
                "output": chat_output,
                "status": chat_result.get("status", "done"),
                "steps": chat_result.get("steps", []),
                "tool_policy": tool_policy,
                "search_policy": search_policy,
                "intent": intent.kind,
                "tool_plan": tool_plan.model_dump() if hasattr(tool_plan, "model_dump") else tool_plan.dict(),
                "tool_results": [tr.model_dump() if hasattr(tr, "model_dump") else tr.dict() for tr in tool_results],
            },
        )
        if status == "done":
            finalize_job(project, job_id, job_update_status)
        else:
            fail_job(project, job_id, job_update_status)
    except Exception as ex:
        message = _format_job_exception(ex)
        write("error", {"error": message, "message": message})
        fail_job(project, job_id, job_update_status)
    finally:
        job_wait_events.pop(job_id, None)


__all__ = [
    "LUMEN_MAX_STEPS_DEFAULT",
    "LUMEN_MAX_STEPS_MAX",
    "LUMEN_MAX_STEPS_MIN",
    "append_job_event",
    "fail_job",
    "finalize_job",
    "run_job_background_service",
    "submit_job_service",
]
