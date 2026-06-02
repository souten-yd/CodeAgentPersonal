from __future__ import annotations

from agent.planner_phase1 import PlannerPhase1
from agent.requirement_schema import RequirementCategoryScores, RequirementDefinition


def _requirement(user_input: str = "Atlas の計画を作る") -> RequirementDefinition:
    return RequirementDefinition(
        requirement_id="req_test",
        source_task_id="task_test",
        user_input=user_input,
        interpreted_goal=user_input,
        user_intent="Test planner fallback handling.",
        task_type="feature",
        functional_requirements=[user_input],
        done_definition=["要件を満たすこと"],
        category_scores=RequirementCategoryScores(),
        ready_for_planning=True,
    )


def _build_plan(raw_payload, user_input: str = "Atlas の計画を作る"):
    planner = PlannerPhase1(lambda _prompt, _content: raw_payload)
    return planner.build_plan(
        requirement=_requirement(user_input),
        planning_mode="standard",
        prompt="Return JSON.",
        nexus_context={},
        repository_context="",
    )


def test_planner_fallback_records_no_implementation_steps_reason() -> None:
    plan = _build_plan({"selected_architecture": "small", "implementation_steps": []})

    assert plan.metadata["planner_fallback"]["reason"] == "no_implementation_steps"
    assert "implementation_steps" in plan.metadata["planner_fallback"]["raw_output_tail"]


def test_planner_fallback_records_parse_error_reason() -> None:
    plan = _build_plan(None)

    assert plan.metadata["planner_fallback"]["reason"] == "parse_error"
    assert plan.implementation_steps[0].action_type == "inspect"


def test_planner_fallback_records_empty_reason() -> None:
    plan = _build_plan({})

    assert plan.metadata["planner_fallback"]["reason"] == "empty"
    assert plan.implementation_steps[0].action_type == "inspect"
