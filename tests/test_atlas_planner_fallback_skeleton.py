from __future__ import annotations

from agent.atlas_plan_pool_builder import AtlasPlanPoolBuilder
from agent.planner_phase1 import PlannerPhase1
from agent.requirement_schema import RequirementCategoryScores, RequirementDefinition


def _requirement(user_input: str) -> RequirementDefinition:
    return RequirementDefinition(
        requirement_id="req_test",
        source_task_id="task_test",
        user_input=user_input,
        interpreted_goal=user_input,
        user_intent="Test simple fallback skeleton.",
        task_type="project_generation",
        functional_requirements=[user_input],
        done_definition=["画面で要件を確認できること"],
        category_scores=RequirementCategoryScores(),
        ready_for_planning=True,
    )


def _fallback_plan(user_input: str):
    planner = PlannerPhase1(lambda _prompt, _content: {"implementation_steps": []})
    return planner.build_plan(
        requirement=_requirement(user_input),
        planning_mode="standard",
        prompt="Return JSON.",
        nexus_context={},
        repository_context="",
    )


def test_simple_html_planner_failure_blocks_without_implementation_skeleton() -> None:
    plan = _fallback_plan("Hello world を表示する HTML を作って。虹色とぼかしアニメも追加。")

    assert plan.status == "needs_replan"
    assert plan.implementation_steps == []
    assert plan.metadata["planner_fallback"]["reason"] == "no_implementation_steps"
    assert plan.metadata["planner_fallback"]["patch_generation_allowed"] is False

    pool = AtlasPlanPoolBuilder().build_from_plan_payload(plan.model_dump(), root_goal=plan.user_goal)
    assert pool.metadata["planner_fallback"]["reason"] == "no_implementation_steps"
    assert pool.status == "needs_revision"
    assert pool.items == []
    assert pool.metadata["patch_generation_allowed"] is False


def test_high_risk_or_unclear_planner_failure_is_not_inspection_fallback() -> None:
    plan = _fallback_plan("本番 database migration を安全に実行する方法を考えて。")

    assert plan.status == "needs_replan"
    assert plan.implementation_steps == []
    assert plan.metadata["planner_fallback"]["patch_generation_allowed"] is False

    pool = AtlasPlanPoolBuilder().build_from_plan_payload(plan.model_dump(), root_goal=plan.user_goal)
    assert pool.status == "needs_revision"
    assert pool.items == []
