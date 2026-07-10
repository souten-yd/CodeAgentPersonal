from __future__ import annotations

from typing import Any

from agent.planner_phase1 import PlannerPhase1
from agent.requirement_schema import RequirementDefinition


class _FlakyThenValidLLM:
    """2-arg callable that returns None (simulating a stalled/failed call) for the first
    ``fail_count`` calls, then a valid plan-generation payload."""

    def __init__(self, fail_count: int) -> None:
        self.fail_count = fail_count
        self.calls = 0

    def __call__(self, _system: str, _user: str) -> Any:
        self.calls += 1
        if self.calls <= self.fail_count:
            return None
        return {
            "implementation_steps": [
                {"title": "Step 1", "description": "Do the thing", "action_type": "inspect"},
            ],
            "selected_architecture": "Incremental additive changes",
        }


def _requirement() -> RequirementDefinition:
    return RequirementDefinition(
        requirement_id="req_001",
        source_task_id="task_001",
        user_input="Build a game.",
        interpreted_goal="Build a game.",
        functional_requirements=["Build a game."],
        non_functional_requirements=[],
        constraints=[],
    )


def test_build_plan_recovers_after_repeated_stalls_within_budget():
    # Reproduces a real live-model bug: build_plan's generate_structured call previously used the
    # default max_attempts=2, and this local model's response time for the large planning prompt
    # (nexus + repository context on top of the user request) routinely exceeded the per-call
    # timeout, burning an attempt on a bare stall (llm_json_fn returning None) with zero output. With
    # only 2 total attempts, one wasted stall left virtually no margin to ever succeed. 4 failures
    # would have exhausted the old budget; the fix widens it to 5 attempts (matching patch
    # generation's MAX_LLM_GENERATION_ATTEMPTS), so a plan can still be produced.
    llm = _FlakyThenValidLLM(fail_count=4)
    planner = PlannerPhase1(llm_json_fn=llm)

    plan = planner.build_plan(
        requirement=_requirement(),
        planning_mode="standard",
        prompt="system prompt",
        nexus_context={},
        repository_context="",
    )

    assert llm.calls == 5
    assert plan.status == "planned"
    assert len(plan.implementation_steps) == 1
    assert "planner_failure_requires_replan" not in planner.get_last_warnings()


def test_build_plan_still_falls_back_when_all_attempts_fail():
    # The bounded retry must still terminate honestly (not retry forever) when the model genuinely
    # never produces a usable plan.
    llm = _FlakyThenValidLLM(fail_count=10)
    planner = PlannerPhase1(llm_json_fn=llm)

    plan = planner.build_plan(
        requirement=_requirement(),
        planning_mode="standard",
        prompt="system prompt",
        nexus_context={},
        repository_context="",
    )

    assert llm.calls == 5
    assert plan.status == "needs_replan"
    assert "planner_failure_requires_replan" in planner.get_last_warnings()
