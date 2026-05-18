from __future__ import annotations

from agent.atlas_supervised_handoff_retry_schema import AtlasSupervisedHandoffRetryPolicy


POLICIES = {
    "supervised_handoff_retry_v1": AtlasSupervisedHandoffRetryPolicy(policy_id="supervised_handoff_retry_v1", name="Supervised Handoff Retry", description="Optional bounded retry for failed/blocked/skipped supervised handoff verification."),
    "supervised_handoff_retry_dry_run_v1": AtlasSupervisedHandoffRetryPolicy(policy_id="supervised_handoff_retry_dry_run_v1", name="Supervised Handoff Retry (Dry Run)", description="Classification only.", allow_bounded_retry=False),
    "strict_supervised_handoff_retry_v1": AtlasSupervisedHandoffRetryPolicy(policy_id="strict_supervised_handoff_retry_v1", name="Strict Supervised Handoff Retry", description="Strict retry policy.", max_attempts=1),
}

def get_supervised_handoff_retry_policy(policy_id: str) -> AtlasSupervisedHandoffRetryPolicy:
    return POLICIES.get(policy_id, POLICIES["supervised_handoff_retry_v1"])

def list_supervised_handoff_retry_policies() -> list[AtlasSupervisedHandoffRetryPolicy]:
    return list(POLICIES.values())
