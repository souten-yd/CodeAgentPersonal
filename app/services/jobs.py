"""Generic job persistence helpers and Lumen compatibility wrappers.

Lumen-specific submission and execution orchestration lives in
``app.services.lumen_runtime``. This module keeps the generic job event helpers
and thin compatibility entry points used by older imports.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


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


def submit_job_service(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Compatibility wrapper for the Lumen submit service."""
    from app.services.lumen_runtime import submit_lumen_job_service

    return submit_lumen_job_service(*args, **kwargs)


def run_job_background_service(*args: Any, **kwargs: Any) -> None:
    """Compatibility wrapper for the Lumen background runtime service."""
    from app.services.lumen_runtime import run_lumen_job_background_service

    return run_lumen_job_background_service(*args, **kwargs)


__all__ = [
    "append_job_event",
    "fail_job",
    "finalize_job",
    "run_job_background_service",
    "submit_job_service",
]
