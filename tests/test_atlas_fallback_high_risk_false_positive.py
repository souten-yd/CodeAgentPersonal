from __future__ import annotations

from agent.planner_phase1 import PlannerPhase1
from agent.planner_phase1 import _contains_high_risk_fallback_intent, _infer_simple_fallback_target
from agent.requirement_schema import RequirementDefinition


def test_do_not_execute_advisory_is_not_high_risk_intent() -> None:
    text = "ADVISORY REPOSITORY CONTEXT - DO NOT EXECUTE\nCreate a simple HTML page."

    assert _contains_high_risk_fallback_intent(text) is False
    assert _contains_high_risk_fallback_intent("エージェントは実行しない。HTML を作って。") is False


def test_true_execution_migration_stays_high_risk() -> None:
    assert _contains_high_risk_fallback_intent("please execute the migration in production") is True


def test_simple_html_fallback_target_survives_advisory_noise() -> None:
    clean = "Hello world の HTML を作って。虹色で、ぼかしも入れて。"
    noisy = f"{clean}\n\nADVISORY REPOSITORY CONTEXT - DO NOT EXECUTE\nadvisory only"

    assert _infer_simple_fallback_target(clean) == "index.html"
    assert _infer_simple_fallback_target(noisy) == "index.html"


def test_missing_planner_steps_generates_html_skeleton_plan() -> None:
    planner = PlannerPhase1(llm_json_fn=lambda _prompt, _input: {"user_goal": "Hello"})
    requirement = RequirementDefinition(
        requirement_id="req1",
        source_task_id="task1",
        user_input="Hello world の HTML を作って。虹色で、ぼかしも入れて。",
        interpreted_goal="Hello world HTML",
    )

    plan = planner.build_plan(
        requirement=requirement,
        planning_mode="standard",
        prompt="prompt",
        nexus_context={},
        repository_context="",
    )

    assert plan.implementation_steps[0].action_type == "create"
    assert plan.implementation_steps[0].target_files == ["index.html"]
    assert "planner_fallback_skeleton_generated" in planner.get_last_warnings()
