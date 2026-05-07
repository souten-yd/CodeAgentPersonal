from agent.atlas_task_decomposer import AtlasTaskDecomposer
from agent.deep_planner_schema import DeepArchitectureOption, DeepPlanPayload, DeepPlanningReflection


def _deep_plan() -> DeepPlanPayload:
    return DeepPlanPayload(
        requirement_id="req1",
        user_goal="大きな改修を段階的に進めたい",
        architecture_options=[DeepArchitectureOption(option_id="A", title="A"), DeepArchitectureOption(option_id="B", title="B", summary="selected", risk_level="low")],
        selected_option_id="B",
        reflection=DeepPlanningReflection(safety_notes=["No file change"]),
        implementation_phases=["Requirement refinement", "Architecture and touchpoint planning", "Implementation plan preparation"],
        verification_strategy=["Tests are mapped"],
        done_definition=["Preview only constraints are explicit"],
    )


def test_decompose_from_deep_plan_generates_multiple_tasks() -> None:
    tasks = AtlasTaskDecomposer().decompose(autopilot_id="auto1", user_goal="goal", deep_plan=_deep_plan())
    assert len(tasks) >= 3
    assert tasks[1].depends_on == [tasks[0].task_id]
    assert tasks[0].acceptance_criteria


def test_fallback_returns_at_least_two_tasks_and_japanese_goal() -> None:
    tasks = AtlasTaskDecomposer().decompose(autopilot_id="auto2", user_goal="日本語の大目標", deep_plan=None)
    assert len(tasks) >= 2
    assert any("日本語" in t.goal for t in tasks)
