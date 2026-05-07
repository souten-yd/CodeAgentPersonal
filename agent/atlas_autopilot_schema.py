from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


AutopilotStatus = Literal["draft", "planned", "preview_ready", "blocked", "failed", "task_plan_ready"]


class AtlasAutopilotRequest(BaseModel):
    autopilot_id: str
    created_at: str = Field(default_factory=_utc_now_iso)
    user_goal: str
    project_path: str = ""
    project_name: str = ""
    requirement_mode: str = "ask_when_needed"
    planning_mode: str = "standard"
    execution_mode: str = "preview_only"
    use_nexus: bool = True
    safety_mode: str = "strict"


class AtlasAutopilotTask(BaseModel):
    task_id: str
    title: str
    description: str = ""
    goal: str = ""
    rationale: str = ""
    expected_output: str = ""
    task_type: str = "other"
    priority: str = "medium"
    depends_on: list[str] = Field(default_factory=list)
    status: str = "planned"
    suggested_planning_mode: str = "standard"
    suggested_requirement_mode: str = "ask_when_needed"
    risk_level: str = "medium"
    estimated_complexity: str = "medium"
    target_areas: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    blocked_reason: str = ""
    linked_requirement_id: str = ""
    linked_plan_id: str = ""
    linked_run_id: str = ""
    plan_status: str = ""
    review_status: str = ""
    plan_markdown_path: str = ""
    requirement_markdown_path: str = ""
    last_plan_message: str = ""


class AtlasAutopilotPlan(BaseModel):
    autopilot_id: str
    user_goal: str
    interpreted_goal: str = ""
    tasks: list[AtlasAutopilotTask] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    safety_constraints: list[str] = Field(default_factory=list)
    done_definition: list[str] = Field(default_factory=list)
    deep_planning: dict | None = None
    selected_architecture_summary: str = ""
    task_decomposition_strategy: str = ""
    execution_order: list[str] = Field(default_factory=list)
    preview_only: bool = True


class AtlasAutopilotRunState(BaseModel):
    autopilot_id: str
    status: AutopilotStatus = "draft"
    current_task_id: str = ""
    completed_task_ids: list[str] = Field(default_factory=list)
    blocked_task_ids: list[str] = Field(default_factory=list)
    failed_task_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    summary: str = ""
    planned_task_ids: list[str] = Field(default_factory=list)
    task_plan_ids: dict[str, str] = Field(default_factory=dict)
    task_requirement_ids: dict[str, str] = Field(default_factory=dict)
