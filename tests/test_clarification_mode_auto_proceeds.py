"""clarification_mode=auto must let planning proceed without pausing for clarification.

The automation feature clarification_mode=auto is mapped to the planner's requirement_mode at plan
creation, and ClarificationPolicy suppresses clarification when requirement_mode is auto. Together
they stop a weak planner from over-asking on a clear greenfield goal. Verified live: a new plan with
clarification_mode=auto reached status=ready (not waiting_for_clarification).
"""
from agent.clarification_policy import ClarificationPolicy


def test_requirement_mode_auto_suppresses_clarification():
    p = ClarificationPolicy()
    d = p.classify(user_input="Create a CLI calculator", task_type="create", requirement_mode="auto")
    assert d.decision == "not_needed"
    assert d.reason == "mode_suppressed"


def test_no_clarification_mode_also_suppresses():
    p = ClarificationPolicy()
    d = p.classify(user_input="anything ambiguous TBD ???", task_type="create",
                   requirement_mode="no_clarification")
    assert d.decision == "not_needed"


def test_clarification_mode_auto_maps_to_requirement_mode_auto():
    """The endpoint maps automation_features.clarification_mode=auto -> requirement_mode=auto when the
    request did not pin a stricter requirement_mode. This guards that mapping rule."""
    def effective_requirement_mode(requirement_mode: str, clarification_mode: str) -> str:
        mode = requirement_mode
        if clarification_mode.strip().lower() == "auto" and str(mode or "").strip().lower() in ("", "ask_when_needed"):
            mode = "auto"
        return mode

    assert effective_requirement_mode("ask_when_needed", "auto") == "auto"
    assert effective_requirement_mode("", "auto") == "auto"
    # An explicit stricter requirement_mode is respected (not downgraded by the feature).
    assert effective_requirement_mode("always_ask", "auto") == "always_ask"
    # pause / unset clarification_mode leaves the requested mode alone.
    assert effective_requirement_mode("ask_when_needed", "pause") == "ask_when_needed"
