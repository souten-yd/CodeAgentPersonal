from __future__ import annotations
from datetime import datetime, timezone
from pydantic import BaseModel, Field

class AtlasPostManualExecutionRefreshRequest(BaseModel):
    pool_id:str; run_id:str=""; workspace_id:str="default"; project_path:str=""; executor_run_id:str
    policy_id:str="post_manual_execution_refresh_v1"; item_status_policy_id:str="supervised_item_status_v1"; multi_status_policy_id:str="multi_item_supervised_status_v1"; orchestrator_policy_id:str="next_action_orchestrator_v1"
    refresh_item_status:bool=True; rebuild_multi_status_queue:bool=True; prepare_next_action:bool=True; use_latest_artifacts:bool=True; dry_run:bool=False
    reviewer:str="manual"; reason:str=""; metadata:dict=Field(default_factory=dict)

class AtlasPostManualExecutionRefreshPolicy(BaseModel):
    policy_id:str; name:str; description:str
    require_executed_or_dry_run_result:bool=True; allow_refresh_item_status:bool=True; allow_rebuild_multi_status_queue:bool=True; allow_prepare_next_action:bool=True
    allow_next_action_execution:bool=False; allow_safe_apply:bool=False; allow_verification:bool=False; allow_bounded_retry:bool=False; allow_patch_regeneration:bool=False; allow_approval:bool=False; allow_auto_continue:bool=False; allow_rollback_restore:bool=False; allow_debug_review:bool=False; allow_remote_git:bool=False
    max_items:int=200; notes:list[str]=Field(default_factory=list)

class AtlasPostManualExecutionRefreshResult(BaseModel):
    pool_id:str; run_id:str; refresh_run_id:str; executor_run_id:str; policy_id:str; status:str
    manual_execution_result:dict=Field(default_factory=dict); item_status_result:dict=Field(default_factory=dict); multi_status_result:dict=Field(default_factory=dict); next_action_orchestrator_result:dict=Field(default_factory=dict)
    refreshed_item_id:str=""; previous_next_action:str=""; next_item_id:str=""; next_action:str=""; next_action_contract:dict=Field(default_factory=dict)
    counts:dict=Field(default_factory=dict); warnings:list[str]=Field(default_factory=list); errors:list[str]=Field(default_factory=list); metadata:dict=Field(default_factory=dict)
    created_at:str=Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
