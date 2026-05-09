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


class JobSubmitRequest(BaseModel):
    """Request body accepted by the legacy POST /jobs/submit route."""

    message: str
    project: str = "default"
    mode: str = "task"
    max_steps: int = 20
    search_enabled: bool | None = None
    llm_url: str = ""
    approved_tasks: list[Any] | None = None
    chat_history: list[Any] = Field(default_factory=list)
    recommended_model: str = ""
    auto_select_option: bool = True
    auto_skill_generation: bool = True


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
