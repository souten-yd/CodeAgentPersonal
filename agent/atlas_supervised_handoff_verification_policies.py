from agent.atlas_supervised_handoff_verification_schema import AtlasSupervisedHandoffVerificationPolicy


POLICIES = {
    "supervised_handoff_verification_v1": AtlasSupervisedHandoffVerificationPolicy(policy_id="supervised_handoff_verification_v1", name="Supervised Handoff Verification", description="Run allowlisted verification + evaluator after applied supervised handoff safe apply."),
    "supervised_handoff_verification_dry_run_v1": AtlasSupervisedHandoffVerificationPolicy(policy_id="supervised_handoff_verification_dry_run_v1", name="Supervised Handoff Verification Dry Run", description="Validate inputs and preview payloads only.", allow_context_refresh=False, allow_evaluator=False),
    "strict_supervised_handoff_verification_v1": AtlasSupervisedHandoffVerificationPolicy(policy_id="strict_supervised_handoff_verification_v1", name="Strict Supervised Handoff Verification", description="Strict post-handoff verification.", max_changed_files=2),
}


def get_supervised_handoff_verification_policy(policy_id: str) -> AtlasSupervisedHandoffVerificationPolicy:
    if policy_id not in POLICIES:
        raise ValueError("unknown_policy")
    return POLICIES[policy_id]


def list_supervised_handoff_verification_policies() -> list[AtlasSupervisedHandoffVerificationPolicy]:
    return list(POLICIES.values())
