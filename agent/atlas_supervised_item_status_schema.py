from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, Field


class AtlasSupervisedItemStatusFinalizeRequest(BaseModel):
    pool_id: str
    item_id: str
    run_id: str = ""
    workspace_id: str = "default"
    project_path: str = ""
    policy_id: str = "supervised_item_status_v1"
    source_run_id: str = ""
    source_type: str = ""
    use_latest_artifacts: bool = True
    update_item_status: bool = True
    update_metadata: bool = True
    dry_run: bool = False
    reviewer: str = "manual"
    reason: str = ""
    metadata: dict = Field(default_factory=dict)


class AtlasSupervisedItemStatusPolicy(BaseModel):
    policy_id: str
    name: str
    description: str
    update_plan_item_status: bool = True
    preserve_original_status: bool = True
    allow_completed: bool = True
    allow_manual_required: bool = True
    allow_needs_revision: bool = True
    allow_patch_candidate_ready: bool = True
    allow_patch_regen_recommended: bool = True
    allow_safe_apply_ready: bool = True
    allow_verification_required: bool = True
    allow_blocked: bool = True
    allow_failed_internal: bool = True
    allow_side_effect_execution: bool = False
    allow_safe_apply: bool = False
    allow_verification: bool = False
    allow_bounded_retry: bool = False
    allow_patch_regeneration: bool = False
    allow_rollback_restore: bool = False
    max_status_history: int = 100
    notes: list[str] = Field(default_factory=list)


class AtlasSupervisedItemTransition(BaseModel):
    from_status: str = ""
    to_status: str
    reason: str
    confidence: float = 1.0
    next_action: str
    next_action_payload: dict = Field(default_factory=dict)
    evidence_type: str = ""
    evidence_run_id: str = ""
    evidence_summary: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class AtlasSupervisedItemStatusFinalizeResult(BaseModel):
    pool_id: str
    item_id: str
    run_id: str
    finalize_run_id: str
    policy_id: str
    status: Literal["finalized", "unchanged", "blocked", "failed_internal", "dry_run"]
    item_status_before: str = ""
    item_status_after: str = ""
    supervised_status_before: str = ""
    supervised_status_after: str = ""
    transition: AtlasSupervisedItemTransition
    selected_evidence: dict = Field(default_factory=dict)
    evidence_index: dict = Field(default_factory=dict)
    next_action: str = ""
    next_action_payload: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
