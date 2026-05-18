from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


class AtlasSupervisedHandoffSafeApplyRequest(BaseModel):
    pool_id: str
    item_id: str
    run_id: str = ""
    workspace_id: str = "default"
    project_path: str = ""
    handoff_id: str
    policy_id: str = "supervised_handoff_safe_apply_v1"
    require_fresh_handoff: bool = True
    require_gate_recheck: bool = True
    require_patch_hash_match: bool = True
    dry_run: bool = False
    reviewer: str = "manual"
    reason: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class AtlasSupervisedHandoffSafeApplyPolicy(BaseModel):
    policy_id: str
    name: str
    description: str
    require_approved_handoff: bool = True
    require_safe_apply_ready: bool = True
    forbid_reapply: bool = True
    require_patch_hash_match: bool = True
    require_gate_recheck: bool = True
    allow_verification: bool = False
    allow_bounded_retry: bool = False
    allow_auto_rollback: bool = False
    allow_auto_restore: bool = False
    allow_auto_debug_review: bool = False
    allow_patch_regeneration: bool = False
    allow_remote_git: bool = False
    max_patch_chars: int = 48000
    max_target_files: int = 10
    notes: list[str] = Field(default_factory=list)


class AtlasSupervisedHandoffSafeApplyResult(BaseModel):
    pool_id: str
    item_id: str
    run_id: str = ""
    handoff_id: str
    execution_id: str
    policy_id: str
    status: Literal["applied", "blocked", "failed", "dry_run"]
    safe_apply_result: dict[str, Any] = Field(default_factory=dict)
    handoff_status_before: dict[str, Any] = Field(default_factory=dict)
    handoff_status_after: dict[str, Any] = Field(default_factory=dict)
    gate_decision: dict[str, Any] = Field(default_factory=dict)
    changed_files: list[str] = Field(default_factory=list)
    snapshot_id: str = ""
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
