from __future__ import annotations

from agent.atlas_multi_item_autopilot_schema import AtlasMultiItemAutopilotPolicy


def list_multi_item_policies() -> list[AtlasMultiItemAutopilotPolicy]:
    return [
        AtlasMultiItemAutopilotPolicy(policy_id="guarded_multi_item_v1", name="Guarded multi-item", description="Low-risk approved guarded multi-item autopilot.", max_items=12),
        # Full-auto is autonomous: a successfully-applied change must not be paused by the
        # evaluator's conservative ``manual_required`` (e.g. a static file whose only verification
        # is "open in a browser"). ``manual_required`` is dropped from stop_decisions so every entry
        # point (orchestrator OR the chat panel's direct /run) behaves autonomously; ``stop`` and
        # ``revise`` remain. Critical/protected/destructive events still pause via the separate
        # critical-event / safety-gate path, not this evaluator decision.
        AtlasMultiItemAutopilotPolicy(policy_id="full_auto_multi_item_v1", name="Full auto multi-item", description="Autonomous code generation: applies low/medium/high-risk create/update items.", max_items=20, allowed_risk_levels=["low", "medium", "high"], require_approval=False, stop_decisions=["stop", "revise"]),
        AtlasMultiItemAutopilotPolicy(policy_id="dry_run_multi_item_v1", name="Dry run multi-item", description="Eligibility/ordering only; no side effects."),
        AtlasMultiItemAutopilotPolicy(policy_id="single_step_guarded_v1", name="Single step guarded", description="One-item guarded flow through multi-item engine.", max_items=1),
    ]


def get_multi_item_policy(policy_id: str) -> AtlasMultiItemAutopilotPolicy:
    for p in list_multi_item_policies():
        if p.policy_id == policy_id:
            return p
    raise ValueError("policy_not_found")
