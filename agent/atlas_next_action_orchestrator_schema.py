from __future__ import annotations
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class AtlasNextActionOrchestratorRequest(BaseModel):
    pool_id: str
    run_id: str = ""
    workspace_id: str = "default"
    project_path: str = ""
    policy_id: str = "next_action_orchestrator_v1"
    multi_status_run_id: str = ""
    item_id: str = ""
    requested_next_action: str = ""
    build_queue_if_missing: bool = True
    refresh_queue: bool = False
    queue_policy_id: str = "multi_item_supervised_status_v1"
    dry_run: bool = False
    reviewer: str = "manual"
    reason: str = ""
    metadata: dict = Field(default_factory=dict)


class AtlasNextActionOrchestratorPolicy(BaseModel):
    policy_id: str
    name: str
    description: str
    allow_prepare_action_contract: bool = True
    allow_execute_action: bool = False
    allow_safe_apply: bool = False
    allow_verification: bool = False
    allow_bounded_retry: bool = False
    allow_patch_regeneration: bool = False
    allow_approval: bool = False
    allow_rollback_restore: bool = False
    allow_remote_git: bool = False
    allow_manual_display_actions: bool = True
    require_selectable_item: bool = True
    require_payload_validated: bool = True
    max_queue_items: int = 200
    notes: list[str] = Field(default_factory=list)


class AtlasNextActionContract(BaseModel):
    action_id: str
    item_id: str
    item_title: str = ""
    supervised_status: str = ""
    next_action: str
    action_kind: str
    target_api_method: str = ""
    target_api_path: str = ""
    target_service: str = ""
    payload: dict = Field(default_factory=dict)
    required_fields: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    payload_valid: bool = False
    selectable: bool = False
    manual_required: bool = True
    execution_allowed: bool = False
    blocked_reason: str = ""
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class AtlasNextActionOrchestratorResult(BaseModel):
    pool_id: str
    run_id: str
    orchestrator_run_id: str
    policy_id: str
    status: str
    multi_status_run_id: str = ""
    selected_item_id: str = ""
    selected_next_action: str = ""
    action_contract: AtlasNextActionContract | None = None
    queue_summary: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
