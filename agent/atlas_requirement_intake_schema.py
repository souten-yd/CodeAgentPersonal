from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


RequirementInputSource = Literal["atlas_workbench", "vue_next", "legacy_ui", "api"]


class AtlasRequirementIntakeRequest(BaseModel):
    input: str
    source: RequirementInputSource | str = "atlas_workbench"
    project_path: str = ""
    project_name: str = "CodeAgentPersonal"
    workspace_id: str = "default"
    planning_depth: str = "standard"
    metadata: dict[str, Any] = Field(default_factory=dict)


class AtlasRequirementIntakeSafety(BaseModel):
    runtime_level: str = "level_0_manual_only"
    backend_workflow_state_authoritative: bool = True
    vue_source_of_truth: bool = False
    vue_execution_capability: str = "none"
    mutation_performed: bool = False
    execution_performed: bool = False
    patch_apply_performed: bool = False
    git_operation_performed: bool = False
    autonomous_execution_enabled: bool = False
    self_modification_enabled: bool = False


class AtlasRequirementIntakePreview(BaseModel):
    schema_version: str = "atlas.requirement_intake_preview.v1"
    contract: str = "read_only_requirement_intake"
    status: str
    source: str
    normalized_input: str
    input_length: int
    can_start_planning: bool
    blocked_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    project_path: str = ""
    project_name: str = "CodeAgentPersonal"
    workspace_id: str = "default"
    planning_depth: str = "standard"
    safety: AtlasRequirementIntakeSafety = Field(default_factory=AtlasRequirementIntakeSafety)
