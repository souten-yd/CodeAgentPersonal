from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, Field

from agent.atlas_plan_target_contract import PLAN_TARGET_CONTRACT_SCHEMA_VERSION, PlanOperation


from agent.atlas_time_utils import utc_now_iso as _utc_now_iso


ActionType = Literal["create", "update", "delete", "inspect", "run_command", "test"]
RiskLevel = Literal["low", "medium", "high"]
PlanningMode = Literal["fast", "standard", "deep_nexus"]
TaskType = Literal["bugfix", "feature", "refactor", "ui", "project_generation", "investigation", "other"]


class ImplementationStep(BaseModel):
    schema_version: str = PLAN_TARGET_CONTRACT_SCHEMA_VERSION
    step_id: str
    title: str
    description: str = ""
    goal: str = ""
    patch_task_kind: str = ""
    requirement_ids: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    target_files: list[str] = Field(default_factory=list)
    target_directories: list[str] = Field(default_factory=list)
    operations: list[PlanOperation] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    normalization_diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    expected_changes: list[str] = Field(default_factory=list)
    action_type: ActionType = "inspect"
    risk_level: RiskLevel = "low"
    verification: str = ""
    verification_contract: dict[str, Any] = Field(default_factory=dict)
    rollback: str = ""
    preserve_behaviors: list[str] = Field(default_factory=list)


class Plan(BaseModel):
    schema_version: str = PLAN_TARGET_CONTRACT_SCHEMA_VERSION
    plan_id: str
    requirement_id: str
    created_at: str = Field(default_factory=_utc_now_iso)
    updated_at: str = Field(default_factory=_utc_now_iso)
    mode: PlanningMode = "standard"
    task_type: TaskType = "other"
    patch_task_kind: str = ""
    original_user_request: str = ""
    user_goal: str = ""
    requirement_summary: str = ""
    requirements: list[dict[str, Any]] = Field(default_factory=list)
    nexus_context_summary: str = ""
    repository_context: str = ""
    assumptions: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    architecture_options: list[str] = Field(default_factory=list)
    selected_architecture: str = ""
    preserve_behaviors: list[str] = Field(default_factory=list)
    rejected_architectures: list[str] = Field(default_factory=list)
    implementation_steps: list[ImplementationStep] = Field(default_factory=list)
    target_files: list[str] = Field(default_factory=list)
    target_directories: list[str] = Field(default_factory=list)
    operations: list[PlanOperation] = Field(default_factory=list)
    normalization_diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    expected_file_changes: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    test_plan: list[str] = Field(default_factory=list)
    verification_plan: list[str] = Field(default_factory=list)
    rollback_plan: list[str] = Field(default_factory=list)
    done_definition: list[str] = Field(default_factory=list)
    destructive_change_detected: bool = False
    requires_user_confirmation: bool = False
    status: str = "planned"
    deep_planning: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
