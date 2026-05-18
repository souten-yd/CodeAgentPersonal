from __future__ import annotations

from agent.atlas_multi_item_autopilot_schema import AtlasMultiItemAutopilotPolicy


def list_multi_item_policies() -> list[AtlasMultiItemAutopilotPolicy]:
    return [
        AtlasMultiItemAutopilotPolicy(policy_id="guarded_multi_item_v1", name="Guarded multi-item", description="Low-risk approved guarded multi-item autopilot."),
        AtlasMultiItemAutopilotPolicy(policy_id="dry_run_multi_item_v1", name="Dry run multi-item", description="Eligibility/ordering only; no side effects."),
        AtlasMultiItemAutopilotPolicy(policy_id="single_step_guarded_v1", name="Single step guarded", description="One-item guarded flow through multi-item engine.", max_items=1),
    ]


def get_multi_item_policy(policy_id: str) -> AtlasMultiItemAutopilotPolicy:
    for p in list_multi_item_policies():
        if p.policy_id == policy_id:
            return p
    raise ValueError("policy_not_found")
