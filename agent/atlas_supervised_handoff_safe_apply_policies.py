from agent.atlas_supervised_handoff_safe_apply_schema import AtlasSupervisedHandoffSafeApplyPolicy


def list_supervised_handoff_safe_apply_policies() -> list[AtlasSupervisedHandoffSafeApplyPolicy]:
    return [
        AtlasSupervisedHandoffSafeApplyPolicy(policy_id="supervised_handoff_safe_apply_v1", name="Default", description="Apply approved handoff safely."),
        AtlasSupervisedHandoffSafeApplyPolicy(policy_id="supervised_handoff_safe_apply_dry_run_v1", name="Dry Run", description="Validation/gate only.", notes=["dry_run_only"]),
        AtlasSupervisedHandoffSafeApplyPolicy(policy_id="strict_supervised_handoff_safe_apply_v1", name="Strict", description="Strict mode.", max_target_files=2, notes=["block_on_warnings", "gate_must_allow_exact"]),
    ]


def get_supervised_handoff_safe_apply_policy(policy_id: str) -> AtlasSupervisedHandoffSafeApplyPolicy:
    for policy in list_supervised_handoff_safe_apply_policies():
        if policy.policy_id == policy_id:
            return policy
    return list_supervised_handoff_safe_apply_policies()[0]
