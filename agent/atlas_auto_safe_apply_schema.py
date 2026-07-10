from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from agent.atlas_auto_policy_presets import DEFAULT_AUTO_POLICY_PRESET_ID


class AtlasAutoSafeApplyRequest(BaseModel):
    pool_id: str
    item_id: str
    preset_id: str = DEFAULT_AUTO_POLICY_PRESET_ID
    workspace_id: str = "default"
    run_id: str = ""
    dry_run_decision_only: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class AtlasAutoSafeApplyResult(BaseModel):
    pool_id: str
    item_id: str
    run_id: str = ""
    preset_id: str
    status: Literal["applied", "blocked", "failed", "skipped", "decision_only"]
    automation_decision: dict[str, Any] = Field(default_factory=dict)
    safe_apply_result: dict[str, Any] = Field(default_factory=dict)
    change_snapshot: dict[str, Any] = Field(default_factory=dict)
    workspace_root: str = ""
    actual_file_changed: bool = False
    changed_files: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    plan_pool: dict[str, Any] | None = None
    orchestration_summary: dict[str, Any] | None = None
    continuation_prompt: str = ""
