from __future__ import annotations

from datetime import datetime, timezone
from pydantic import BaseModel, Field


class AtlasPatchRegenRecommendationRequest(BaseModel):
    pool_id: str
    item_id: str
    run_id: str = ""
    workspace_id: str = "default"
    project_path: str = ""
    handoff_id: str = ""
    safe_apply_execution_id: str = ""
    verification_run_id: str = ""
    supervised_retry_run_id: str = ""
    policy_id: str = "patch_regen_recommendation_v1"
    patch_regen_policy_id: str = "supervised_patch_regen_v1"
    require_retry_terminal: bool = True
    dry_run: bool = False
    reviewer: str = "manual"
    reason: str = ""
    metadata: dict = Field(default_factory=dict)


class AtlasPatchRegenRecommendationPolicy(BaseModel):
    policy_id: str
    name: str
    description: str
    eligible_retry_statuses: list[str] = Field(default_factory=lambda: ["exhausted", "not_retryable", "stopped"])
    eligible_verification_statuses: list[str] = Field(default_factory=lambda: ["failed"])
    require_failure_evidence: bool = True
    require_original_patch: bool = True
    require_target_files: bool = True
    require_deterministic_or_exhausted_signal: bool = True
    allow_transient_only: bool = False
    allow_auto_patch_regen: bool = False
    allow_safe_apply: bool = False
    allow_verification: bool = False
    allow_bounded_retry: bool = False
    allow_auto_rollback: bool = False
    allow_auto_restore: bool = False
    allow_auto_debug_review: bool = False
    allow_remote_git: bool = False
    max_target_files: int = 10
    max_payload_chars: int = 64000
    notes: list[str] = Field(default_factory=list)


class AtlasPatchRegenRecommendedPayload(BaseModel):
    pool_id: str
    item_id: str
    run_id: str = ""
    workspace_id: str = "default"
    project_path: str = ""
    policy_id: str = "supervised_patch_regen_v1"
    context_bundle_id: str = ""
    retry_run_id: str = ""
    evaluator_result_id: str = ""
    verification_result: dict = Field(default_factory=dict)
    bounded_retry_result: dict = Field(default_factory=dict)
    failure_stop_suggestion: dict = Field(default_factory=dict)
    original_patch: str = ""
    changed_files: list[str] = Field(default_factory=list)
    target_files: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class AtlasPatchRegenRecommendationResult(BaseModel):
    pool_id: str
    item_id: str
    run_id: str
    handoff_id: str = ""
    safe_apply_execution_id: str = ""
    verification_run_id: str = ""
    supervised_retry_run_id: str = ""
    recommendation_run_id: str
    policy_id: str
    patch_regen_policy_id: str
    status: str
    recommended_payload: AtlasPatchRegenRecommendedPayload | None
    retry_result: dict = Field(default_factory=dict)
    verification_result: dict = Field(default_factory=dict)
    safe_apply_execution_result: dict = Field(default_factory=dict)
    handoff: dict = Field(default_factory=dict)
    eligibility: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
