from __future__ import annotations
from pydantic import BaseModel, Field

ALLOWED_GUARDED_LOOP_MODES={"advance_to_confirmation","dry_run_next_action","execute_confirmed_action","refresh_after_execution","execute_and_refresh"}
ALLOWED_GUARDED_LOOP_ACTIONS={"approve_patch_candidate","run_supervised_safe_apply","run_supervised_verification","run_supervised_retry","run_patch_regen_from_recommendation","manual_review","investigate_failure","none"}
ALLOWED_GUARDED_LOOP_EXPLICIT_DECISIONS={"","approve","reject","hold"}

class AtlasGuardedOperatorLoopRequest(BaseModel):
    pool_id:str
    run_id:str=""
    workspace_id:str="default"
    project_path:str=""
    policy_id:str="guarded_operator_loop_v1"
    mode:str="advance_to_confirmation"
    multi_status_run_id:str=""
    orchestrator_run_id:str=""
    executor_run_id:str=""
    action_id:str=""
    expected_next_action:str=""
    confirmation_token:str=""
    confirmation_text:str=""
    explicit_decision:str=""
    require_dry_run_first:bool=True
    dry_run:bool=False
    reviewer:str="manual"
    reason:str=""
    metadata:dict=Field(default_factory=dict)

class AtlasGuardedOperatorLoopPolicy(BaseModel):
    policy_id:str; name:str; description:str
    allow_queue_build:bool=True; allow_prepare_next_action:bool=True; allow_token_preview:bool=True; allow_auto_dry_run:bool=True
    allow_execute_confirmed_action:bool=True; allow_post_execution_refresh:bool=True; allow_prepare_after_refresh:bool=True
    allow_execute_without_confirmation:bool=False; allow_execute_without_dry_run:bool=False; allow_multi_action:bool=False; allow_execute_all:bool=False; allow_auto_continue:bool=False
    allow_rollback_restore:bool=False; allow_debug_review:bool=False; allow_remote_git:bool=False
    max_actions_per_request:int=1; max_auto_steps_per_request:int=5; max_items:int=200
    notes:list[str]=Field(default_factory=list)

class AtlasGuardedOperatorLoopStep(BaseModel):
    step:str; status:str; run_id:str=""; result_id:str=""; summary:dict=Field(default_factory=dict); warnings:list[str]=Field(default_factory=list); errors:list[str]=Field(default_factory=list)

class AtlasGuardedOperatorLoopResult(BaseModel):
    pool_id:str; run_id:str; loop_run_id:str; policy_id:str; mode:str; status:str
    multi_status_run_id:str=""; orchestrator_run_id:str=""; executor_run_id:str=""; post_refresh_run_id:str=""
    selected_item_id:str=""; selected_next_action:str=""; action_id:str=""; action_kind:str=""
    confirmation_token:str=""; confirmation_text:str="EXECUTE ONE ACTION"
    action_contract:dict=Field(default_factory=dict); dry_run_result:dict=Field(default_factory=dict); execute_result:dict=Field(default_factory=dict); refresh_result:dict=Field(default_factory=dict); next_action_summary:dict=Field(default_factory=dict)
    steps:list[AtlasGuardedOperatorLoopStep]=Field(default_factory=list); warnings:list[str]=Field(default_factory=list); errors:list[str]=Field(default_factory=list); metadata:dict=Field(default_factory=dict); created_at:str=""
