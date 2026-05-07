from agent.deep_planner import DeepPlanner
from agent.requirement_schema import RequirementDefinition


def _req(user_input: str = "要件を整理したい") -> RequirementDefinition:
    return RequirementDefinition(
        requirement_id="req_deep_001",
        source_task_id="task_001",
        user_input=user_input,
        interpreted_goal="Atlas計画品質を高める",
        user_intent="Deep planning",
    )


def test_deep_planner_returns_three_options_and_selected():
    planner = DeepPlanner(llm_json_fn=lambda _p, _i: {})
    result = planner.build_deep_plan(requirement=_req(), prompt="x", nexus_context={}, repository_context="repo")
    assert len(result.architecture_options) == 3
    assert {o.option_id for o in result.architecture_options} == {"A", "B", "C"}
    assert result.selected_option_id in {"A", "B", "C"}
    rejected = [o for o in result.architecture_options if o.option_id != result.selected_option_id]
    assert all(o.why_rejected for o in rejected)


def test_deep_planner_fallback_keeps_three_options_and_japanese_input():
    planner = DeepPlanner(llm_json_fn=lambda _p, _i: None)
    result = planner.build_deep_plan(requirement=_req("日本語の要件でも壊れないこと"), prompt="x", nexus_context={}, repository_context="repo")
    assert len(result.architecture_options) == 3
    assert result.user_goal
    assert result.reflection.safety_notes


def test_deep_planner_does_not_mutate_files_field():
    planner = DeepPlanner(llm_json_fn=lambda _p, _i: {})
    result = planner.build_deep_plan(requirement=_req(), prompt="x", nexus_context={}, repository_context="repo")
    assert result.requirement_id == "req_deep_001"
