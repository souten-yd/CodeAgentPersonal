from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AtlasRepoContextRequest(BaseModel):
    workspace_id: str = "default"
    project_path: str = ""
    pool_id: str = ""
    run_id: str = ""
    changed_files: list[str] = Field(default_factory=list)
    target_files: list[str] = Field(default_factory=list)
    goal: str = ""
    mode: Literal["latest_only", "impacts", "related_tests", "scope_summary"] = "latest_only"
    allow_build_if_missing: bool = False
    max_impacted_files: int = 100
    max_related_tests: int = 50
    metadata: dict = Field(default_factory=dict)


class AtlasRepoContextSnapshot(BaseModel):
    status: Literal["available", "missing", "partial", "blocked", "failed_internal"] = "missing"
    workspace_id: str = "default"
    project_path: str = ""
    project_hash: str = ""
    index_run_id: str = ""
    index_status: str = ""
    changed_files: list[str] = Field(default_factory=list)
    target_files: list[str] = Field(default_factory=list)
    impacted_files: list[str] = Field(default_factory=list)
    impacted_symbols: list[str] = Field(default_factory=list)
    related_tests: list[str] = Field(default_factory=list)
    related_tests_by_file: dict = Field(default_factory=dict)
    dependency_summary: dict = Field(default_factory=dict)
    route_summary: dict = Field(default_factory=dict)
    ui_event_summary: dict = Field(default_factory=dict)
    confidence_by_file: dict = Field(default_factory=dict)
    reason_by_file: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class AtlasPlanScopeSummary(BaseModel):
    status: str = "missing"
    scope_source: Literal["repo_index", "plan_items", "user_input", "missing"] = "missing"
    target_files: list[str] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    impacted_files: list[str] = Field(default_factory=list)
    related_tests: list[str] = Field(default_factory=list)
    likely_modules: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low", "unknown"] = "unknown"
    repo_index_snapshot: AtlasRepoContextSnapshot | dict = Field(default_factory=dict)
