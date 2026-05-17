from __future__ import annotations

from agent.atlas_llm_evaluator_schema import AtlasEvaluatorPolicy


def list_evaluator_policies() -> list[AtlasEvaluatorPolicy]:
    return [
        AtlasEvaluatorPolicy(policy_id="guarded_evaluator_v1", name="Guarded Evaluator v1", description="Default guarded evaluator policy."),
        AtlasEvaluatorPolicy(policy_id="manual_review_only", name="Manual Review Only", description="Always require manual review.", allow_llm=False),
        AtlasEvaluatorPolicy(policy_id="strict_failure_guard", name="Strict Failure Guard", description="Never continue after verification failure.", allow_continue_on_failed_verification=False),
    ]


def get_evaluator_policy(policy_id: str) -> AtlasEvaluatorPolicy:
    for p in list_evaluator_policies():
        if p.policy_id == policy_id:
            return p
    return list_evaluator_policies()[0]
