from agent.atlas_manual_next_action_executor_schema import AtlasManualNextActionExecutorPolicy

def list_manual_next_action_executor_policies():
    return [
        AtlasManualNextActionExecutorPolicy(policy_id="manual_next_action_executor_v1",name="Manual Next Action Executor",description="execute one action with explicit confirmation"),
        AtlasManualNextActionExecutorPolicy(policy_id="manual_next_action_executor_dry_run_v1",name="Manual Next Action Executor (dry-run only)",description="validation only",require_confirmation_token=False),
        AtlasManualNextActionExecutorPolicy(policy_id="strict_manual_next_action_executor_v1",name="Strict Manual Next Action Executor",description="no approval/safe_apply",allow_approval=False,allow_safe_apply=False),
    ]

def get_manual_next_action_executor_policy(policy_id:str)->AtlasManualNextActionExecutorPolicy:
    for p in list_manual_next_action_executor_policies():
        if p.policy_id==policy_id:return p
    return list_manual_next_action_executor_policies()[0]
