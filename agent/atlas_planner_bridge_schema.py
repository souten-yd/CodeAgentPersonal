from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from agent.atlas_plan_pool_schema import AtlasPlanPool


AtlasPlannerBridgeMode = Literal["auto", "real_planner", "fallback_only"]
AtlasPlannerBridgeStatus = Literal[
    "planned",
    "waiting_for_clarification",
    "fallback_used",
    "planner_failed",
    "skipped",
]


class AtlasPlannerBridgeRequest(BaseModel):
    input: str
    project_path: str = ""
    project_name: str = "CodeAgentPersonal"
    planning_depth: str = "standard"
    automation_level: str = "plan_then_ask"
    execution_strategy: str = "sequential"
    requirement_mode: str = "ask_when_needed"
    use_nexus: bool = True
    mode: AtlasPlannerBridgeMode = "auto"
    pool_id: str = ""
    workspace_id: str = "default"
    metadata: dict = Field(default_factory=dict)
    repo_context_package: dict = Field(default_factory=dict)
    planner_context_text: str = ""


class AtlasPlannerBridgeResult(BaseModel):
    status: AtlasPlannerBridgeStatus
    pool: AtlasPlanPool | None = None
    planner_result: dict = Field(default_factory=dict)
    requirement: dict = Field(default_factory=dict)
    plan: dict = Field(default_factory=dict)
    review_result: dict = Field(default_factory=dict)
    questions: list[dict] = Field(default_factory=list)
    plan_payload: dict = Field(default_factory=dict)
    used_fallback: bool = False
    fallback_reason: str = ""
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    repo_context_package: dict = Field(default_factory=dict)
    planner_context_text: str = ""
