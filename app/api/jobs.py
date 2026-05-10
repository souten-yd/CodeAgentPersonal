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

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.lumen.budgets import (
    LumenNewsBudget,
    LumenSearchBudget,
    LumenWeatherBudget,
)
from app.services.lumen_runtime import (
    LUMEN_CHAT_MODES,
    LUMEN_LEGACY_MODES,
    LUMEN_MAX_STEPS_DEFAULT,
    LUMEN_MAX_STEPS_MAX,
    LUMEN_MAX_STEPS_MIN,
    clamp_lumen_max_steps,
    legacy_task_mode_removed_payload,
    normalize_lumen_job_mode,
    resolve_lumen_search_policy,
    validate_lumen_submit_request,
)

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


class JobSubmitRequest(BaseModel):
    """Request body accepted by POST /jobs/submit for Lumen chat jobs."""

    message: str
    project: str = "default"
    mode: str = "chat"
    max_steps: int = LUMEN_MAX_STEPS_DEFAULT
    search_enabled: bool | None = None
    tool_policy: str = "auto"
    search_policy: str = "auto"
    search_budget: LumenSearchBudget = Field(default_factory=LumenSearchBudget)
    weather_budget: LumenWeatherBudget = Field(default_factory=LumenWeatherBudget)
    news_budget: LumenNewsBudget = Field(default_factory=LumenNewsBudget)
    location: str | None = None
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
    """Compatibility shim for Lumen submit; /lumen/submit is primary."""
    try:
        validate_lumen_submit_request(req)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)

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
