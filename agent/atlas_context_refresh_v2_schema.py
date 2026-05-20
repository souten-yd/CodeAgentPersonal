from __future__ import annotations

from pydantic import BaseModel, Field


_SAFETY_METADATA = {
    "advisory_only": True,
    "executed": False,
    "shell_executed": False,
    "remote_git_executed": False,
    "auto_verification_triggered": False,
    "auto_test_execution_triggered": False,
    "no_auto_build": True,
    "no_execution": True,
    "commands_are_suggestions_only": True,
    "context_refresh_v2": True,
}


class AtlasContextRefreshV2Request(BaseModel):
    workspace_id: str = "default"
    project_path: str = ""
    pool_id: str = ""
    item_id: str = ""
    goal: str = ""
    changed_files: list[str] = Field(default_factory=list)
    target_files: list[str] = Field(default_factory=list)
    plan_pool: dict = Field(default_factory=dict)
    impact_map: dict = Field(default_factory=dict)
    include_repo_context: bool = True
    include_plan_item_impact_map: bool = True
    allow_build_if_missing: bool = False
    metadata: dict = Field(default_factory=dict)


class AtlasContextRefreshV2Bundle(BaseModel):
    status: str = "missing"
    workspace_id: str = "default"
    project_path: str = ""
    pool_id: str = ""
    item_id: str = ""
    goal: str = ""
    scope: dict = Field(default_factory=dict)
    plan_item_impact: dict = Field(default_factory=dict)
    impacted_files: list[str] = Field(default_factory=list)
    related_tests: list[str] = Field(default_factory=list)
    recommended_commands: list[str] = Field(default_factory=list)
    manual_verification_steps: list[str] = Field(default_factory=list)
    ci_selection_hints: list[dict] = Field(default_factory=list)
    evidence: list[dict] = Field(default_factory=list)
    context_notes: list[str] = Field(default_factory=list)
    confidence: str = "unknown"
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=lambda: dict(_SAFETY_METADATA))
