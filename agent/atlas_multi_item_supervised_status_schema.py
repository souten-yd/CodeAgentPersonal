from __future__ import annotations

from datetime import datetime, timezone
from pydantic import BaseModel, Field


class AtlasMultiItemSupervisedStatusRequest(BaseModel):
    pool_id: str
    run_id: str = ""
    workspace_id: str = "default"
    project_path: str = ""
    policy_id: str = "multi_item_supervised_status_v1"
    item_ids: list[str] = Field(default_factory=list)
    use_latest_artifacts: bool = True
    refresh_item_status: bool = True
    update_item_status: bool = True
    update_metadata: bool = True
    dry_run: bool = False
    include_completed: bool = True
    include_blocked: bool = True
    include_manual_required: bool = True
    include_next_action_payloads: bool = True
    max_items: int = 200
    reviewer: str = "manual"
    reason: str = ""
    metadata: dict = Field(default_factory=dict)


class AtlasMultiItemSupervisedStatusPolicy(BaseModel):
    policy_id: str
    name: str
    description: str
    refresh_item_status: bool = True
    update_item_status: bool = True
    allow_next_action_execution: bool = False
    allow_safe_apply: bool = False
    allow_verification: bool = False
    allow_bounded_retry: bool = False
    allow_patch_regeneration: bool = False
    allow_approval: bool = False
    allow_rollback_restore: bool = False
    allow_remote_git: bool = False
    max_items: int = 200
    preferred_next_actions: list[str] = Field(default_factory=lambda: ["approve_patch_candidate", "run_supervised_safe_apply", "run_supervised_verification", "run_supervised_retry", "run_patch_regen_from_recommendation", "manual_review", "investigate_failure"])
    notes: list[str] = Field(default_factory=list)


class AtlasMultiItemSupervisedItemSummary(BaseModel):
    item_id: str
    item_title: str = ""
    item_status: str = ""
    supervised_status: str = ""
    next_action: str = ""
    next_action_payload: dict = Field(default_factory=dict)
    evidence_type: str = ""
    evidence_run_id: str = ""
    priority: int = 100
    selectable: bool = True
    blocked_reason: str = ""
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class AtlasMultiItemSupervisedStatusResult(BaseModel):
    pool_id: str
    run_id: str
    multi_status_run_id: str
    policy_id: str
    status: str
    item_summaries: list[AtlasMultiItemSupervisedItemSummary] = Field(default_factory=list)
    next_item: AtlasMultiItemSupervisedItemSummary | None = None
    next_actions_by_type: dict = Field(default_factory=dict)
    counts: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
