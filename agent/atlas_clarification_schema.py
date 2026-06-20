from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


from agent.atlas_time_utils import utc_now_iso as _utc_now_iso


class AtlasClarificationAnswer(BaseModel):
    question_id: str
    answer: str | list[str] = ""
    skipped: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class AtlasClarificationSession(BaseModel):
    session_id: str
    workspace_id: str = "default"
    # The pool_id the original plan-create request reserved. Reused when the answered plan is built
    # so the pool_id the caller has been tracking stays stable (no surprise new id / dead 404).
    original_pool_id: str = ""
    original_input: str
    project_path: str = ""
    project_name: str = "CodeAgentPersonal"
    planner_mode: str = "auto"
    requirement_mode: str = "ask_when_needed"
    planning_depth: str = "standard"
    automation_level: str = "plan_then_ask"
    execution_strategy: str = "sequential"
    questions: list[dict[str, Any]] = Field(default_factory=list)
    answers: list[AtlasClarificationAnswer] = Field(default_factory=list)
    requirement: dict[str, Any] = Field(default_factory=dict)
    status: str = "waiting_for_clarification"
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=_utc_now_iso)
    updated_at: str = Field(default_factory=_utc_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AtlasClarificationSubmitRequest(BaseModel):
    session_id: str = ""
    pool_id: str = ""  # original reserved pool_id to reuse for the answered plan (optional)
    original_input: str = ""
    answers: list[AtlasClarificationAnswer] = Field(default_factory=list)
    project_path: str = ""
    project_name: str = "CodeAgentPersonal"
    planner_mode: str = "auto"
    requirement_mode: str = "ask_when_needed"
    planning_depth: str = "standard"
    automation_level: str = "plan_then_ask"
    execution_strategy: str = "sequential"
    workspace_id: str = "default"
    metadata: dict[str, Any] = Field(default_factory=dict)


class AtlasClarificationSubmitResult(BaseModel):
    status: str
    session: AtlasClarificationSession | None = None
    pool: dict[str, Any] = Field(default_factory=dict)
    questions: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
