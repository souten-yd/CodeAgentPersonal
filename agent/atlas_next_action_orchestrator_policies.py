from agent.atlas_next_action_orchestrator_schema import AtlasNextActionOrchestratorPolicy


def list_next_action_orchestrator_policies():
    return [
        AtlasNextActionOrchestratorPolicy(policy_id="next_action_orchestrator_v1", name="Next Action Orchestrator", description="Prepare only", max_queue_items=200),
        AtlasNextActionOrchestratorPolicy(policy_id="next_action_orchestrator_dry_run_v1", name="Next Action Orchestrator Dry Run", description="Preview only", max_queue_items=200),
        AtlasNextActionOrchestratorPolicy(policy_id="strict_next_action_orchestrator_v1", name="Strict Next Action Orchestrator", description="Execution-candidate only", max_queue_items=200),
    ]


def get_next_action_orchestrator_policy(policy_id: str):
    for p in list_next_action_orchestrator_policies():
        if p.policy_id == policy_id:
            return p
    raise ValueError(f"unknown_policy:{policy_id}")
