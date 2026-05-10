"""Job API router.

This router owns lightweight job status reads and the submit route split from
``main.py``. Provider lookups preserve production ``main.app`` behavior, while
provider-less ``create_app()`` returns conservative fallback payloads without
opening job storage, starting background work, or touching LLM/ASR/TTS runtime
state.
"""

from collections.abc import Callable
from copy import deepcopy
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

router = APIRouter()

ProjectJobsProvider = Callable[..., Any]
JobPollProvider = Callable[..., Any]
JobSubmitProvider = Callable[..., Any]

PROJECT_JOBS_DEFAULT_PAYLOAD: dict[str, Any] = {"jobs": []}
JOB_POLL_DEFAULT_PAYLOAD: dict[str, Any] = {"status": "done", "steps": []}
JOB_SUBMIT_DEFAULT_PAYLOAD: dict[str, Any] = {
    "ok": False,
    "status": "unavailable",
    "job_id": None,
    "message": "job submit provider unavailable",
}


LUMEN_SEARCH_POLICIES = {"off", "auto", "on"}
LUMEN_LEGACY_MODES = {"task", "agent_task", "legacy_task"}
LUMEN_CHAT_MODES = {None, "", "chat", "lumen", "conversation"}

LUMEN_MAX_STEPS_DEFAULT = 8
LUMEN_MAX_STEPS_MIN = 1
LUMEN_MAX_STEPS_MAX = 20


def _clamp_int(value: Any, *, default: int, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(min_value, min(max_value, parsed))


def normalize_lumen_job_mode(mode: str | None) -> str:
    """Normalize Lumen aliases and reject removed task modes.

    Task-like modes are not silently mapped to chat because stale clients should
    fail fast instead of reintroducing legacy task execution into Lumen.
    """
    normalized = "" if mode is None else str(mode).strip().lower()
    if normalized in LUMEN_LEGACY_MODES:
        raise ValueError("legacy_task_mode_removed")
    if normalized in {"", "chat", "lumen", "conversation"}:
        return "chat"
    raise ValueError("unsupported_lumen_job_mode")


def normalize_lumen_search_policy(search_policy: str | None) -> str:
    if search_policy is None:
        return "auto"
    normalized = str(search_policy).strip().lower()
    if normalized not in LUMEN_SEARCH_POLICIES:
        raise ValueError("unsupported_lumen_search_policy")
    return normalized


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


class LumenSearchBudget(BaseModel):
    """One-shot lightweight web-assist limits for Lumen chat jobs."""

    max_queries: int = 3
    max_results_per_query: int = 5
    max_fetch_pages: int = 3
    max_total_chars: int = 12000
    timeout_sec: int = 20


def clamp_lumen_search_budget(budget: LumenSearchBudget | dict[str, Any] | None) -> LumenSearchBudget:
    raw: dict[str, Any]
    if budget is None:
        raw = {}
    elif isinstance(budget, LumenSearchBudget):
        raw = budget.model_dump() if hasattr(budget, "model_dump") else budget.dict()
    elif isinstance(budget, dict):
        raw = budget
    else:
        raw = {}
    return LumenSearchBudget(
        max_queries=_clamp_int(raw.get("max_queries"), default=3, min_value=0, max_value=5),
        max_results_per_query=_clamp_int(raw.get("max_results_per_query"), default=5, min_value=1, max_value=10),
        max_fetch_pages=_clamp_int(raw.get("max_fetch_pages"), default=3, min_value=0, max_value=5),
        max_total_chars=_clamp_int(raw.get("max_total_chars"), default=12000, min_value=2000, max_value=30000),
        timeout_sec=_clamp_int(raw.get("timeout_sec"), default=20, min_value=5, max_value=60),
    )


class JobSubmitRequest(BaseModel):
    """Request body accepted by POST /jobs/submit for Lumen chat jobs."""

    message: str
    project: str = "default"
    mode: str = "chat"
    max_steps: int = LUMEN_MAX_STEPS_DEFAULT
    search_enabled: bool | None = None
    search_policy: str = "auto"
    search_budget: LumenSearchBudget = Field(default_factory=LumenSearchBudget)
    llm_url: str = ""
    chat_history: list[Any] = Field(default_factory=list)


def default_project_jobs_payload() -> dict[str, Any]:
    """Return an empty job list without opening the job registry or filesystem."""
    return deepcopy(PROJECT_JOBS_DEFAULT_PAYLOAD)


def default_job_poll_payload() -> dict[str, Any]:
    """Return an empty completed poll payload without touching job execution."""
    return deepcopy(JOB_POLL_DEFAULT_PAYLOAD)


def default_job_submit_payload() -> dict[str, Any]:
    """Return a safe submit fallback without starting job execution."""
    return deepcopy(JOB_SUBMIT_DEFAULT_PAYLOAD)


def get_project_jobs_provider(request: Request) -> ProjectJobsProvider | None:
    """Look up the optional app-state provider for project job lists."""
    provider = getattr(request.app.state, "project_jobs_provider", None)
    if callable(provider):
        return provider
    return None


def get_job_poll_provider(request: Request) -> JobPollProvider | None:
    """Look up the optional app-state provider for job polling."""
    provider = getattr(request.app.state, "job_poll_provider", None)
    if callable(provider):
        return provider
    return None


def get_job_submit_provider(request: Request) -> JobSubmitProvider | None:
    """Look up the optional app-state provider for job submission."""
    provider = getattr(request.app.state, "job_submit_provider", None)
    if callable(provider):
        return provider
    return None


@router.post("/jobs/submit")
def submit_job_api(req: JobSubmitRequest, request: Request) -> Any:
    try:
        req.mode = normalize_lumen_job_mode(req.mode)
        req.search_policy = resolve_lumen_search_policy(req.search_enabled, req.search_policy)
        req.max_steps = clamp_lumen_max_steps(req.max_steps)
        req.search_budget = clamp_lumen_search_budget(req.search_budget)
    except ValueError as exc:
        if str(exc) == "legacy_task_mode_removed":
            return JSONResponse(status_code=410, content=legacy_task_mode_removed_payload())
        return JSONResponse(
            status_code=422,
            content={"ok": False, "error": str(exc), "message": "Unsupported Lumen job submit option."},
        )

    provider = get_job_submit_provider(request)
    if provider is not None:
        return provider(req)
    return default_job_submit_payload()


@router.get("/projects/{project}/jobs")
def get_project_jobs_api(project: str, request: Request, limit: int = 30) -> Any:
    provider = get_project_jobs_provider(request)
    if provider is not None:
        return provider(project, limit=limit)
    return default_project_jobs_payload()


@router.get("/jobs/{job_id}/poll")
def get_job_poll_api(
    job_id: str,
    request: Request,
    project: str = "default",
    after: int = -1,
) -> Any:
    provider = get_job_poll_provider(request)
    if provider is not None:
        return provider(job_id, project=project, after=after)
    return default_job_poll_payload()
