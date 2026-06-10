"""Twin projection job coordination with startup recovery (PI-4).

Projection (build/refresh) work is queued as jobs so an interrupted process can resume or
safely retry after restart (ADR-PI-011 journal/outbox semantics). This module does not bind
to a specific store: it operates on an injected ``JobStore`` (structurally satisfied by
``agent.project_intelligence.store.ProjectIntelligenceStore``), so the twin core does not
import a concrete Atlas store. Composition happens at the factory/test boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol


class JobStore(Protocol):
    """Structural interface for the restart-safe job journal."""

    def enqueue_job(self, *, project_id: str, workspace_id: str, job_id: str,
                    job_type: str, payload: dict[str, Any] | None = ...,
                    idempotency_key: str | None = ...) -> str: ...
    def claim_job(self, project_id: str, job_id: str) -> dict[str, Any] | None: ...
    def complete_job(self, project_id: str, job_id: str, *, status: str = ...,
                     error: str | None = ...) -> None: ...
    def recover_running_jobs(self, project_id: str) -> int: ...
    def get_job(self, project_id: str, job_id: str) -> dict[str, Any] | None: ...
    def list_jobs(self, project_id: str, *, status: str | None = ...) -> list[dict[str, Any]]: ...


BUILD = "twin_full_build"
REFRESH = "twin_incremental_refresh"

_MAX_ATTEMPTS = 3


@dataclass(frozen=True)
class ProjectionOutcome:
    job_id: str
    status: str
    attempts: int
    error: str | None = None


class ProjectionJobService:
    """Schedules and runs twin projection jobs with bounded retry and restart recovery."""

    def __init__(self, store: JobStore, *, max_attempts: int = _MAX_ATTEMPTS) -> None:
        self._store = store
        self._max_attempts = max_attempts

    def schedule(
        self,
        *,
        project_id: str,
        workspace_id: str,
        job_id: str,
        job_type: str = BUILD,
        payload: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> str:
        return self._store.enqueue_job(
            project_id=project_id, workspace_id=workspace_id, job_id=job_id,
            job_type=job_type, payload=payload, idempotency_key=idempotency_key,
        )

    def recover_on_startup(self, project_id: str) -> int:
        """Requeue jobs left running by an interrupted process. Idempotent."""
        return self._store.recover_running_jobs(project_id)

    def run_one(
        self,
        project_id: str,
        job_id: str,
        handler: Callable[[dict[str, Any]], None],
    ) -> ProjectionOutcome:
        """Claim and run one job. Bounded retry: exceeding max attempts fails the job.

        The handler does the actual projection. Any handler exception leaves the job
        retryable (it returns to 'queued') until max attempts, after which it is failed
        — never silently dropped or marked done.
        """
        job = self._store.claim_job(project_id, job_id)
        if job is None:
            existing = self._store.get_job(project_id, job_id)
            status = existing["status"] if existing else "unknown"
            return ProjectionOutcome(job_id=job_id, status=status,
                                     attempts=existing["attempts"] if existing else 0)
        try:
            handler(job["payload"])
        except Exception as exc:  # retry/fail — never mark done on error
            if job["attempts"] >= self._max_attempts:
                self._store.complete_job(project_id, job_id, status="failed", error=str(exc))
                return ProjectionOutcome(job_id=job_id, status="failed",
                                         attempts=job["attempts"], error=str(exc))
            # Return to queue for another attempt.
            self._store.recover_running_jobs(project_id)
            return ProjectionOutcome(job_id=job_id, status="queued", attempts=job["attempts"],
                                     error=str(exc))
        self._store.complete_job(project_id, job_id, status="done")
        return ProjectionOutcome(job_id=job_id, status="done", attempts=job["attempts"])
