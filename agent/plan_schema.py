from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, Field


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


ActionType = Literal["create", "update", "delete", "inspect", "run_command", "test"]
RiskLevel = Literal["low", "medium", "high"]
PlanningMode = Literal["fast", "standard", "deep_nexus"]
TaskType = Literal["bugfix", "feature", "refactor", "ui", "project_generation", "investigation", "other"]


class ImplementationStep(BaseModel):
    step_id: str
    title: str
    description: str = ""
    target_files: list[str] = Field(default_factory=list)
    action_type: ActionType = "inspect"
    risk_level: RiskLevel = "low"
    verification: str = ""
    rollback: str = ""


class Plan(BaseModel):
    plan_id: str
    requirement_id: str
    created_at: str = Field(default_factory=_utc_now_iso)
    updated_at: str = Field(default_factory=_utc_now_iso)
    mode: PlanningMode = "standard"
    task_type: TaskType = "other"
    user_goal: str = ""
    requirement_summary: str = ""
    nexus_context_summary: str = ""
    repository_context: str = ""
    assumptions: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    architecture_options: list[str] = Field(default_factory=list)
    selected_architecture: str = ""
    rejected_architectures: list[str] = Field(default_factory=list)
    implementation_steps: list[ImplementationStep] = Field(default_factory=list)
    target_files: list[str] = Field(default_factory=list)
    expected_file_changes: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    test_plan: list[str] = Field(default_factory=list)
    verification_plan: list[str] = Field(default_factory=list)
    rollback_plan: list[str] = Field(default_factory=list)
    done_definition: list[str] = Field(default_factory=list)
    destructive_change_detected: bool = False
    requires_user_confirmation: bool = False
    status: str = "planned"
