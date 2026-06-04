"""Contract: a post-clarification apply-time safety *block* must surface as the recoverable
``blocked_safety_review`` status (with a visible reason), NOT a generic ``approval_required`` that
does not survive the apply-time gate (which produced the silent Patch 0/N spinner).
"""
from __future__ import annotations

from agent.atlas_clarification_replanning_service import AtlasClarificationReplanningService
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool


def _service() -> AtlasClarificationReplanningService:
    return AtlasClarificationReplanningService()


def test_next_status_maps_safety_decisions_to_distinct_statuses():
    svc = _service()
    assert svc._next_status({}, {"decision": "allow"}, False) == "ready"
    # A hard block becomes its own recoverable state, not approval_required.
    assert svc._next_status({}, {"decision": "block"}, False) == "blocked_safety_review"
    # A soft require_manual (approval bookkeeping) is still a normal approval gate.
    assert svc._next_status({}, {"decision": "require_manual"}, False) == "approval_required"
    # Critical / raised-risk paths win over the safety decision branch.
    assert svc._next_status({"critical_event": {"critical_event": True}}, {"decision": "block"}, False) == "waiting_for_critical_decision"
    assert svc._next_status({}, {"decision": "block"}, True) == "approval_required"


def test_revise_after_answers_blocks_with_visible_reason():
    # A medium-risk item is blocked by the guarded_low_risk preset at apply time.
    pool = AtlasPlanPool(
        pool_id="pool_block",
        root_goal="Build a multi-file feature",
        status="approval_required",
        project_path="/tmp/ws",
        items=[
            AtlasPlanItem(
                item_id="i1", pool_id="pool_block", title="Item", goal="Do",
                item_type="implementation", status="approval_required", risk_level="medium",
                target_files=["src/i1.py"], metadata={"action_type": "create"},
            )
        ],
        metadata={"clarification_answers": [{"question_id": "q1", "option_id": "minimal_scope", "answer_text": "one file"}]},
    )

    result = _service().revise_after_answers(pool)

    assert result["status"] == "blocked_safety_review"
    assert pool.status == "blocked_safety_review"
    # The block reason is surfaced (not a silent spinner) and recorded for the UI / override flow.
    reason = pool.metadata["safety_gate_block_reason_after_clarification"]
    assert reason and "risk_not_allowed" in reason
    assert result["safety_gate_block_reason_after_clarification"] == reason
    assert "safety block reason" in pool.metadata["gate_rerun_summary"]
    # A fresh revision starts with no override granted; a human must grant it explicitly.
    assert pool.metadata["safety_override_granted_after_clarification"] is False
    assert "override" in pool.metadata["next_required_user_action"].lower()
