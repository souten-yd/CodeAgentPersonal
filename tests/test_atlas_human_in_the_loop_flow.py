"""WS-Verify: end-to-end consistency of the human-in-the-loop boundary.

The same critical_handling knob (Features) must produce a consistent decision at BOTH the
plan-time critique gate (apply_plan_quality_gate) and the apply-time full_auto gate
(relax_evaluation_for_full_auto). ask -> pause for approval, block -> stop, auto -> proceed.
"""
from __future__ import annotations

import pytest

from agent.atlas_autopilot_policy_schema import AtlasPolicyEvaluation
from agent.atlas_full_auto_gate import relax_evaluation_for_full_auto
from agent.atlas_plan_quality_gate import apply_plan_quality_gate


def _security_plan():
    return {
        "requirement_summary": "handle auth tokens",
        "goal": "store credentials",
        "adversarial_critique": {
            "findings": [{"angle": "", "severity": "high", "category": "security",
                          "title": "auth", "detail": "credential handling is unsafe", "recommendation": ""}],
            "consensus_risk": "high",
            "requires_revision": False,
        },
    }


def _security_eval():
    # An apply-time evaluation carrying a safety-sensitive (security) category.
    return AtlasPolicyEvaluation(
        evaluation_id="ev", scope="patch", decision="require_approval",
        categories=["security"], requires_user_confirmation=True,
    )


@pytest.mark.parametrize(
    "handling, plan_requires_approval, plan_revision, apply_decision",
    [
        ("ask", True, False, "require_approval"),
        ("block", True, True, "block"),
        ("auto", False, False, "allow"),
    ],
)
def test_critical_handling_consistent_across_plan_and_apply(handling, plan_requires_approval, plan_revision, apply_decision):
    plan_gate = apply_plan_quality_gate(_security_plan(), preset_id="autonomous_bounded_dev", critical_handling=handling)
    assert plan_gate["require_approval"] is plan_requires_approval
    assert plan_gate["plan_revision_required"] is plan_revision

    apply_gate = relax_evaluation_for_full_auto(_security_eval(), preset_id="full_auto", critical_handling=handling)
    assert apply_gate.decision == apply_decision


def test_hard_block_categories_ignore_handling_at_apply():
    # critical/delete/run_command always block regardless of the knob.
    for cat in ("critical_risk", "delete_forbidden", "run_command_forbidden"):
        ev = AtlasPolicyEvaluation(evaluation_id="e", scope="item", decision="block", categories=[cat], blocked=True)
        for handling in ("ask", "block", "auto"):
            out = relax_evaluation_for_full_auto(ev, preset_id="full_auto", critical_handling=handling)
            assert out.decision == "block", (cat, handling)


def test_quality_categories_always_relax_under_full_auto_regardless_of_handling():
    # Pure quality findings (not safety-sensitive) relax to allow for any handling value.
    ev = AtlasPolicyEvaluation(evaluation_id="e", scope="patch", decision="require_approval",
                               categories=["dependency_change"], requires_user_confirmation=True)
    for handling in ("ask", "block", "auto"):
        out = relax_evaluation_for_full_auto(ev, preset_id="full_auto", critical_handling=handling)
        assert out.decision == "allow", handling
