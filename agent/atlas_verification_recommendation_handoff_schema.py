from __future__ import annotations

from pydantic import BaseModel, Field


class AtlasVerificationRecommendationHandoffRequest(BaseModel):
    workspace_id: str = "default"
    project_path: str = ""
    pool_id: str = ""
    run_id: str = ""
    item_id: str = ""
    action_id: str = ""
    goal: str = ""
    plan_pool: dict = Field(default_factory=dict)
    plan_item: dict = Field(default_factory=dict)
    verification_recommendation: dict = Field(default_factory=dict)
    include_verification_recommendation: bool = True
    allow_build_if_missing: bool = False
    metadata: dict = Field(default_factory=dict)


class AtlasVerificationRecommendationHandoff(BaseModel):
    status: str = "missing"
    workspace_id: str = "default"
    project_path: str = ""
    pool_id: str = ""
    run_id: str = ""
    item_id: str = ""
    action_id: str = ""
    goal: str = ""
    summary: str = ""
    approval_summary: str = ""
    impacted_files: list[str] = Field(default_factory=list)
    related_tests: list[str] = Field(default_factory=list)
    recommended_commands: list[str] = Field(default_factory=list)
    manual_verification_steps: list[str] = Field(default_factory=list)
    ci_selection_hints: list[dict] = Field(default_factory=list)
    confidence: str = "unknown"
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    handoff_metadata: dict = Field(default_factory=dict)
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
        "verification_recommendation_handoff": True,
        "manual_approval_only": True,
    })
