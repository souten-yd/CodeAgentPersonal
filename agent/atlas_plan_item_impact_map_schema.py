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
}


class AtlasPlanItemImpactMapRequest(BaseModel):
    workspace_id: str = "default"
    project_path: str = ""
    pool_id: str = ""
    goal: str = ""
    changed_files: list[str] = Field(default_factory=list)
    target_files: list[str] = Field(default_factory=list)
    plan_pool: dict = Field(default_factory=dict)
    allow_build_if_missing: bool = False
    metadata: dict = Field(default_factory=dict)


class AtlasPlanItemImpact(BaseModel):
    item_id: str = ""
    title: str = ""
    action_type: str = ""
    risk_level: str = ""
    target_files: list[str] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    impacted_files: list[str] = Field(default_factory=list)
    related_tests: list[str] = Field(default_factory=list)
    impacted_symbols: list[str] = Field(default_factory=list)
    recommended_commands: list[str] = Field(default_factory=list)
    manual_verification_steps: list[str] = Field(default_factory=list)
    ci_selection_hints: list[dict] = Field(default_factory=list)
    confidence: str = "unknown"
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=lambda: dict(_SAFETY_METADATA))


class AtlasPlanItemImpactMap(BaseModel):
    status: str = "missing"
    workspace_id: str = "default"
    project_path: str = ""
    pool_id: str = ""
    goal: str = ""
    item_count: int = 0
    impacts: list[AtlasPlanItemImpact] = Field(default_factory=list)
    global_impacted_files: list[str] = Field(default_factory=list)
    global_related_tests: list[str] = Field(default_factory=list)
    global_recommended_commands: list[str] = Field(default_factory=list)
    confidence: str = "unknown"
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=lambda: dict(_SAFETY_METADATA))
