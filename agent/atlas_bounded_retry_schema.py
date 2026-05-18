from __future__ import annotations

from datetime import datetime, timezone
from pydantic import BaseModel, Field


class AtlasBoundedRetryRequest(BaseModel):
    pool_id: str
    item_id: str
    run_id: str = ""
    workspace_id: str = "default"
    project_path: str = ""
    policy_id: str = "verification_retry_v1"
    context_policy_id: str = "local_first_bounded"
    evaluator_policy_id: str = "strict_failure_guard"
    verification_result: dict = Field(default_factory=dict)
    safe_apply_result: dict = Field(default_factory=dict)
    failure_stop_suggestion: dict = Field(default_factory=dict)
    context_bundle_id: str = ""
    changed_files: list[str] = Field(default_factory=list)
    max_attempts: int = 2
    retry_on_statuses: list[str] = Field(default_factory=lambda: ["failed", "blocked", "skipped"])
    dry_run: bool = False
    metadata: dict = Field(default_factory=dict)


class AtlasBoundedRetryPolicy(BaseModel):
    policy_id: str
    name: str
    description: str
    max_attempts: int = 2
    max_runtime_seconds: int = 180
    retry_on_statuses: list[str] = Field(default_factory=lambda: ["failed", "blocked", "skipped"])
    retryable_error_patterns: list[str] = Field(default_factory=list)
    non_retryable_error_patterns: list[str] = Field(default_factory=list)
    require_same_changed_files: bool = True
    allow_context_refresh: bool = True
    allow_evaluator: bool = True
    allow_verification_rerun: bool = True
    allow_safe_apply_rerun: bool = False
    allow_auto_restore: bool = False
    allow_auto_rollback: bool = False
    allow_auto_debug_review: bool = False
    allow_auto_patch_regeneration: bool = False
    notes: list[str] = Field(default_factory=list)


class AtlasRetryAttemptResult(BaseModel):
    attempt_index: int
    status: str
    retry_allowed: bool
    retry_reason: str = ""
    verification_result: dict = Field(default_factory=dict)
    context_bundle_id: str = ""
    evaluator_result_id: str = ""
    evaluator_decision: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class AtlasBoundedRetryResult(BaseModel):
    pool_id: str
    item_id: str
    run_id: str
    retry_run_id: str
    policy_id: str
    status: str
    final_verification_status: str = ""
    attempts: list[AtlasRetryAttemptResult] = Field(default_factory=list)
    attempt_count: int = 0
    stop_reason: str = ""
    context_bundle_id: str = ""
    evaluator_result_id: str = ""
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
