from agent.atlas_guarded_operator_loop_schema import AtlasGuardedOperatorLoopPolicy

def list_guarded_operator_loop_policies():
    return [
        AtlasGuardedOperatorLoopPolicy(policy_id='guarded_operator_loop_v1',name='Guarded Loop v1',description='queue/prepare/token/dry_run/execute/refresh one action'),
        AtlasGuardedOperatorLoopPolicy(policy_id='guarded_operator_loop_prepare_only_v1',name='Prepare only',description='queue/prepare/token only',allow_auto_dry_run=False,allow_execute_confirmed_action=False,allow_post_execution_refresh=False,allow_prepare_after_refresh=False),
        AtlasGuardedOperatorLoopPolicy(policy_id='guarded_operator_loop_dry_run_only_v1',name='Dry-run only',description='queue/prepare/token/dry_run only',allow_execute_confirmed_action=False,allow_post_execution_refresh=False,allow_prepare_after_refresh=False),
        AtlasGuardedOperatorLoopPolicy(policy_id='strict_guarded_operator_loop_v1',name='Strict guarded',description='no approvals execute, no execute_and_refresh',allow_execute_confirmed_action=False),
    ]

def get_guarded_operator_loop_policy(policy_id:str)->AtlasGuardedOperatorLoopPolicy:
    for p in list_guarded_operator_loop_policies():
        if p.policy_id==policy_id: return p
    return list_guarded_operator_loop_policies()[0]
