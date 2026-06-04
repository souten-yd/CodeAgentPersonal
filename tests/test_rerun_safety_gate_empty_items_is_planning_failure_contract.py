"""Contract: an empty/degenerate revised plan (no gateable items, the "fallback-only test plan"
case) must be reported as a *planning failure* that should be repaired/re-planned — NOT a generic
safety "block" dead-end the user cannot escape.
"""
from __future__ import annotations

import pytest

from agent.atlas_clarification_replanning_service import (
    AtlasClarificationReplanningService,
    AtlasPlanningFailure,
)
from agent.atlas_plan_pool_schema import AtlasPlanPool


def test_rerun_safety_gate_raises_planning_failure_for_empty_items():
    with pytest.raises(AtlasPlanningFailure):
        AtlasClarificationReplanningService._rerun_safety_gate(
            AtlasPlanPool(pool_id="p", root_goal="g", status="approval_required", items=[]),
            None,
            "guarded_low_risk",
        )


def test_revise_after_answers_on_empty_plan_is_planning_failure_not_block():
    pool = AtlasPlanPool(
        pool_id="pool_empty",
        root_goal="Goal",
        status="approval_required",
        items=[],
        metadata={"clarification_answers": [{"question_id": "q1", "option_id": "minimal_scope"}]},
    )

    result = AtlasClarificationReplanningService().revise_after_answers(pool)

    assert result["status"] == "failed"
    assert result["failure_kind"] == "planning_failure"
    assert "planning_failure_after_clarification" in result["blocked_reasons"]
    assert pool.metadata["planning_failure_after_clarification"] is True
    # Not a generic safety block; the pool is NOT left at blocked_safety_review.
    assert pool.status != "blocked_safety_review"
    # The user is told this is a planning failure with a clear, actionable next step.
    action = pool.metadata["next_required_user_action"]
    assert "planning failure" in action.lower()
    assert "re-plan" in pool.metadata["revised_plan_summary"].lower()
