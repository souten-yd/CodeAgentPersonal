from __future__ import annotations

from pydantic import BaseModel, Field


class AtlasRepoContextPlannerPackage(BaseModel):
    status: str = "missing"
    package_id: str = ""
    workspace_id: str = "default"
    project_path: str = ""
    project_hash: str = ""
    index_run_id: str = ""
    goal: str = ""
    changed_files: list[str] = Field(default_factory=list)
    target_files: list[str] = Field(default_factory=list)
    impacted_files: list[str] = Field(default_factory=list)
    related_tests: list[str] = Field(default_factory=list)
    impacted_symbols: list[str] = Field(default_factory=list)
    likely_modules: list[str] = Field(default_factory=list)
    route_hints: list[str] = Field(default_factory=list)
    ui_event_hints: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)
    confidence: str = "unknown"
    planner_context_text: str = ""
    recommended_test_plan: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class AtlasImpactedTestRecommendation(BaseModel):
    status: str = "missing"
    changed_files: list[str] = Field(default_factory=list)
    target_files: list[str] = Field(default_factory=list)
    related_tests: list[str] = Field(default_factory=list)
    recommended_commands: list[str] = Field(default_factory=list)
    test_selection_reason: dict = Field(default_factory=dict)
    confidence: str = "unknown"
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
