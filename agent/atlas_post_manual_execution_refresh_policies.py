from agent.atlas_post_manual_execution_refresh_schema import AtlasPostManualExecutionRefreshPolicy
POLICIES={
"post_manual_execution_refresh_v1":AtlasPostManualExecutionRefreshPolicy(policy_id="post_manual_execution_refresh_v1",name="Post manual execution refresh",description="Refresh status and prepare next manual step."),
"post_manual_execution_refresh_dry_run_v1":AtlasPostManualExecutionRefreshPolicy(policy_id="post_manual_execution_refresh_dry_run_v1",name="Post manual execution refresh dry run",description="Validate executor result and preview refresh steps."),
"strict_post_manual_execution_refresh_v1":AtlasPostManualExecutionRefreshPolicy(policy_id="strict_post_manual_execution_refresh_v1",name="Strict post manual execution refresh",description="Executed-only refresh policy."),
}
def get_post_manual_execution_refresh_policy(policy_id:str)->AtlasPostManualExecutionRefreshPolicy: return POLICIES.get(policy_id) or POLICIES["post_manual_execution_refresh_v1"]
def list_post_manual_execution_refresh_policies()->list[AtlasPostManualExecutionRefreshPolicy]: return list(POLICIES.values())
