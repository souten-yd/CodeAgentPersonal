from __future__ import annotations

from datetime import datetime, timezone
from pydantic import BaseModel, Field


class AtlasSupervisedHandoffRetryRequest(BaseModel):
    pool_id: str
    item_id: str
    run_id: str = ""
    workspace_id: str = "default"
    project_path: str = ""
    handoff_id: str = ""
    safe_apply_execution_id: str
    verification_run_id: str
    policy_id: str = "supervised_handoff_retry_v1"
    bounded_retry_policy_id: str = "verification_retry_v1"
    evaluator_policy_id: str = "guarded_evaluator_v1"
    context_policy_id: str = "local_first_bounded"
    require_failed_or_blocked_verification: bool = True
    max_attempts: int = 2
    dry_run: bool = False
    reviewer: str = "manual"
    reason: str = ""
    metadata: dict = Field(default_factory=dict)


class AtlasSupervisedHandoffRetryPolicy(BaseModel):
    policy_id: str
    name: str
    description: str
    require_failed_or_blocked_verification: bool = True
    allow_retry_on_statuses: list[str] = Field(default_factory=lambda: ["failed", "blocked", "skipped"])
    allow_bounded_retry: bool = True
    allow_safe_apply_rerun: bool = False
    allow_patch_regeneration: bool = False
    allow_auto_rollback: bool = False
    allow_auto_restore: bool = False
    allow_auto_debug_review: bool = False
    allow_remote_git: bool = False
    max_attempts: int = 2
    notes: list[str] = Field(default_factory=list)


class AtlasSupervisedHandoffRetryResult(BaseModel):
    pool_id: str
    item_id: str
    run_id: str
    handoff_id: str
    safe_apply_execution_id: str
    verification_run_id: str
    supervised_retry_run_id: str
    bounded_retry_run_id: str = ""
    policy_id: str
    bounded_retry_policy_id: str
    status: str
    original_verification_status: str = ""
    final_verification_status: str = ""
    bounded_retry_result: dict = Field(default_factory=dict)
    retryability: dict = Field(default_factory=dict)
    failure_stop_suggestion: dict = Field(default_factory=dict)
    evaluator_result_id: str = ""
    evaluator_decision: dict = Field(default_factory=dict)
    changed_files: list[str] = Field(default_factory=list)
    snapshot_id: str = ""
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
