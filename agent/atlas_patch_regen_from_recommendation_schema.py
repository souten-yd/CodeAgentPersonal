from __future__ import annotations

from datetime import datetime, timezone
from pydantic import BaseModel, Field


class AtlasPatchRegenFromRecommendationRequest(BaseModel):
    pool_id: str
    item_id: str
    run_id: str = ""
    workspace_id: str = "default"
    project_path: str = ""
    recommendation_run_id: str
    policy_id: str = "patch_regen_from_recommendation_v1"
    patch_regen_policy_id: str = "supervised_patch_regen_v1"
    require_recommendation_ready: bool = True
    require_manual_trigger: bool = True
    allow_reexecute: bool = False
    dry_run: bool = False
    reviewer: str = "manual"
    reason: str = ""
    metadata: dict = Field(default_factory=dict)


class AtlasPatchRegenFromRecommendationPolicy(BaseModel):
    policy_id: str
    name: str
    description: str
    require_recommendation_ready: bool = True
    require_recommended_payload: bool = True
    require_manual_trigger: bool = True
    require_no_prior_execution: bool = True
    allow_patch_regen_execution: bool = True
    allow_safe_apply: bool = False
    allow_verification: bool = False
    allow_bounded_retry: bool = False
    allow_auto_rollback: bool = False
    allow_auto_restore: bool = False
    allow_auto_debug_review: bool = False
    allow_remote_git: bool = False
    max_target_files: int = 10
    max_original_patch_chars: int = 48000
    notes: list[str] = Field(default_factory=list)


class AtlasPatchRegenFromRecommendationResult(BaseModel):
    pool_id: str
    item_id: str
    run_id: str
    recommendation_run_id: str
    recommendation_exec_id: str
    policy_id: str
    patch_regen_policy_id: str
    status: str
    patch_regen_result_id: str = ""
    patch_regen_result: dict = Field(default_factory=dict)
    recommendation_result: dict = Field(default_factory=dict)
    recommended_payload: dict = Field(default_factory=dict)
    validation: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
