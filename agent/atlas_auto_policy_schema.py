from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AtlasAutoPolicyPreset(BaseModel):
    preset_id: str
    name: str
    description: str
    automation_level: Literal["manual_only", "guarded_low_risk", "supervised_auto", "full_autopilot"]
    allow_auto_safe_apply: bool = False
    allow_auto_verification: bool = False
    allow_auto_debug_review: bool = False
    allow_auto_patch_proposal: bool = False
    allow_auto_restore: bool = False
    max_auto_items_per_run: int = 0
    max_changed_files_per_item: int = 1
    allowed_action_types: list[str] = Field(default_factory=lambda: ["update"])
    allowed_item_types: list[str] = Field(default_factory=lambda: ["implementation", "documentation"])
    allowed_risk_levels: list[str] = Field(default_factory=lambda: ["low"])
    forbidden_action_types: list[str] = Field(default_factory=lambda: ["delete", "run_command"])
    require_snapshot_before_apply: bool = True
    require_executor_readable_patch: bool = True
    require_project_path: bool = True
    require_planitem_approval: bool = True
    require_patch_proposal_approval: bool = True
    stop_on_verification_failure: bool = True
    stop_on_content_missing: bool = True
    stop_on_unsafe_path: bool = True
    stop_on_missing_snapshot: bool = True
    notes: list[str] = Field(default_factory=list)


class AtlasAutomationDecision(BaseModel):
    pool_id: str
    item_id: str
    preset_id: str
    decision: Literal["allow", "require_manual", "block"]
    phase: Literal["pre_safe_apply", "post_safe_apply", "pre_verification", "failure_handling"] = "pre_safe_apply"
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
