from __future__ import annotations
from datetime import datetime, timezone
from pydantic import BaseModel, Field

class AtlasManualNextActionExecutorRequest(BaseModel):
    pool_id: str
    run_id: str = ""
    workspace_id: str = "default"
    project_path: str = ""
    orchestrator_run_id: str
    policy_id: str = "manual_next_action_executor_v1"
    action_id: str = ""
    expected_next_action: str = ""
    confirmation_token: str = ""
    confirmation_text: str = ""
    require_dry_run_first: bool = True
    dry_run: bool = True
    reviewer: str = "manual"
    reason: str = ""
    explicit_decision: str = ""
    metadata: dict = Field(default_factory=dict)

class AtlasManualNextActionExecutorPolicy(BaseModel):
    policy_id: str; name: str; description: str
    allow_execute_one_action: bool = True
    require_orchestrator_contract: bool = True
    require_action_ready_status: bool = True
    require_confirmation_token: bool = True
    require_confirmation_text: bool = True
    require_dry_run_before_execute: bool = True
    allow_approval: bool = True
    allow_safe_apply: bool = True
    allow_verification: bool = True
    allow_bounded_retry: bool = True
    allow_patch_regeneration: bool = True
    allow_manual_display_execution: bool = False
    allow_multi_action: bool = False
    allow_auto_continue: bool = False
    allow_rollback_restore: bool = False
    allow_debug_review: bool = False
    allow_remote_git: bool = False
    max_payload_chars: int = 64000
    notes: list[str] = Field(default_factory=list)

class AtlasManualNextActionExecutionResult(BaseModel):
    pool_id: str; run_id: str; executor_run_id: str; orchestrator_run_id: str; policy_id: str; status: str
    selected_item_id: str = ""; selected_next_action: str = ""; action_id: str = ""; action_kind: str = ""
    target_service: str = ""; target_api_path: str = ""; execution_result_id: str = ""
    execution_result: dict = Field(default_factory=dict)
    orchestrator_result: dict = Field(default_factory=dict)
    action_contract: dict = Field(default_factory=dict)
    validation: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
