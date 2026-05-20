from __future__ import annotations

from pydantic import BaseModel, Field


class AtlasCITestSelectionHint(BaseModel):
    label: str = ""
    reason: str = ""
    metadata: dict = Field(default_factory=dict)


class AtlasVerificationPlanItemHint(BaseModel):
    item_id: str = ""
    related_tests: list[str] = Field(default_factory=list)
    recommended_commands: list[str] = Field(default_factory=list)
    manual_steps: list[str] = Field(default_factory=list)
    ci_hints: list[AtlasCITestSelectionHint] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class AtlasVerificationPlanningRequest(BaseModel):
    workspace_id: str = "default"
    project_path: str = ""
    goal: str = ""
    changed_files: list[str] = Field(default_factory=list)
    target_files: list[str] = Field(default_factory=list)
    impacted_files: list[str] = Field(default_factory=list)
    allow_build_if_missing: bool = False


class AtlasVerificationPlan(BaseModel):
    status: str = "missing"
    workspace_id: str = "default"
    project_path: str = ""
    goal: str = ""
    changed_files: list[str] = Field(default_factory=list)
    target_files: list[str] = Field(default_factory=list)
    impacted_files: list[str] = Field(default_factory=list)
    related_tests: list[str] = Field(default_factory=list)
    recommended_commands: list[str] = Field(default_factory=list)
    manual_verification_steps: list[str] = Field(default_factory=list)
    ci_selection_hints: list[AtlasCITestSelectionHint] = Field(default_factory=list)
    per_item_hints: list[AtlasVerificationPlanItemHint] = Field(default_factory=list)
    confidence: str = "unknown"
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=lambda: {
        "advisory_only": True,
        "commands_are_suggestions_only": True,
        "executed": False,
        "shell_executed": False,
        "remote_git_executed": False,
        "auto_verification_triggered": False,
        "auto_test_execution_triggered": False,
        "no_auto_build": True,
        "no_execution": True,
    })
