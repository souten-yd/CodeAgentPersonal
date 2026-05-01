from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


RunStatus = Literal["pending", "running", "completed", "completed_with_skips", "failed", "blocked"]
ExecutionMode = Literal["dry_run", "safe_apply"]
StepStatus = Literal["pending", "running", "completed", "skipped", "blocked", "failed"]


class ImplementationStepResult(BaseModel):
    step_id: str
    title: str
    action_type: str
    risk_level: str
    target_files: list[str] = Field(default_factory=list)
    status: StepStatus = "pending"
    started_at: str = ""
    finished_at: str = ""
    message: str = ""
    changed_files: list[str] = Field(default_factory=list)
    skipped_reason: str = ""
    error: str = ""
    log: list[str] = Field(default_factory=list)


class ImplementationRun(BaseModel):
    run_id: str
    plan_id: str
    requirement_id: str
    approval_id: str
    created_at: str = Field(default_factory=_utc_now_iso)
    updated_at: str = Field(default_factory=_utc_now_iso)
    status: RunStatus = "pending"
    execution_mode: ExecutionMode = "dry_run"
    project_path: str = ""
    total_steps: int = 0
    completed_steps: int = 0
    skipped_steps: int = 0
    failed_steps: int = 0
    blocked_steps: int = 0
    step_results: list[ImplementationStepResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    summary: str = ""
    no_destructive_actions: bool = True


class ImplementationRunRequest(BaseModel):
    execution_mode: ExecutionMode = "dry_run"
    project_path: str = ""
    allow_update: bool = False
    allow_create: bool = False
    allow_delete: bool = False
    allow_run_command: bool = False
    user_comment: str = ""
