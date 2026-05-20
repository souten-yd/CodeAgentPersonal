from __future__ import annotations

from pydantic import BaseModel, Field


class AtlasVerificationRecommendationRequest(BaseModel):
    workspace_id: str = "default"
    project_path: str = ""
    pool_id: str = ""
    item_id: str = ""
    goal: str = ""
    changed_files: list[str] = Field(default_factory=list)
    target_files: list[str] = Field(default_factory=list)
    plan_pool: dict = Field(default_factory=dict)
    planner_packaging_v2: dict = Field(default_factory=dict)
    planner_context_text_v2: str = ""
    include_planner_packaging_v2: bool = True
    allow_build_if_missing: bool = False
    metadata: dict = Field(default_factory=dict)


class AtlasVerificationRecommendation(BaseModel):
    status: str = "missing"
    workspace_id: str = "default"
    project_path: str = ""
    pool_id: str = ""
    item_id: str = ""
    goal: str = ""
    summary: str = ""
    impacted_files: list[str] = Field(default_factory=list)
    related_tests: list[str] = Field(default_factory=list)
    recommended_commands: list[str] = Field(default_factory=list)
    manual_verification_steps: list[str] = Field(default_factory=list)
    ci_selection_hints: list[dict] = Field(default_factory=list)
    evidence: list[dict] = Field(default_factory=list)
    confidence: str = "unknown"
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=lambda: {
        "advisory_only": True,
        "executed": False,
        "shell_executed": False,
        "remote_git_executed": False,
        "auto_verification_triggered": False,
        "auto_test_execution_triggered": False,
        "no_auto_build": True,
        "no_execution": True,
        "commands_are_suggestions_only": True,
        "verification_recommendation": True,
    })
