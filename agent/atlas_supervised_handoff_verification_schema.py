from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


class AtlasSupervisedHandoffVerificationRequest(BaseModel):
    pool_id: str
    item_id: str
    run_id: str = ""
    workspace_id: str = "default"
    project_path: str = ""
    handoff_id: str = ""
    safe_apply_execution_id: str
    policy_id: str = "supervised_handoff_verification_v1"
    context_policy_id: str = "local_first_bounded"
    evaluator_policy_id: str = "guarded_evaluator_v1"
    require_applied_safe_apply: bool = True
    require_fresh_safe_apply_result: bool = True
    require_allowlisted_verification: bool = True
    include_context_refresh: bool = True
    include_evaluator: bool = True
    dry_run: bool = False
    reviewer: str = "manual"
    reason: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class AtlasSupervisedHandoffVerificationPolicy(BaseModel):
    policy_id: str
    name: str
    description: str
    require_applied_safe_apply: bool = True
    require_handoff_safe_apply_executed: bool = True
    forbid_reverification: bool = True
    require_allowlisted_verification: bool = True
    allow_context_refresh: bool = True
    allow_evaluator: bool = True
    allow_bounded_retry: bool = False
    allow_auto_rollback: bool = False
    allow_auto_restore: bool = False
    allow_auto_debug_review: bool = False
    allow_patch_regeneration: bool = False
    allow_safe_apply_rerun: bool = False
    allow_remote_git: bool = False
    max_changed_files: int = 20
    notes: list[str] = Field(default_factory=list)


class AtlasSupervisedHandoffVerificationResult(BaseModel):
    pool_id: str
    item_id: str
    run_id: str
    handoff_id: str
    safe_apply_execution_id: str
    verification_run_id: str
    policy_id: str
    status: Literal["passed", "failed", "blocked", "skipped", "dry_run", "evaluator_manual_required", "evaluator_stop", "failed_internal"]
    verification_result: dict[str, Any] = Field(default_factory=dict)
    safe_apply_execution_result: dict[str, Any] = Field(default_factory=dict)
    handoff_status_before: dict[str, Any] = Field(default_factory=dict)
    handoff_status_after: dict[str, Any] = Field(default_factory=dict)
    context_bundle_id: str = ""
    evaluator_result_id: str = ""
    evaluator_decision: dict[str, Any] = Field(default_factory=dict)
    failure_stop_suggestion: dict[str, Any] = Field(default_factory=dict)
    changed_files: list[str] = Field(default_factory=list)
    snapshot_id: str = ""
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
