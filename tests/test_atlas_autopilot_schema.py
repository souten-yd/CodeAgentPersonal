from agent.atlas_autopilot_schema import AtlasAutopilotPlan, AtlasAutopilotRequest, AtlasAutopilotTask


def test_atlas_autopilot_request_creation_with_japanese() -> None:
    req = AtlasAutopilotRequest(
        autopilot_id="auto_test_1",
        user_goal="NovelConverterのOCRとTTS統合を改善したい",
        project_path="/workspace/project",
        project_name="NovelConverter",
    )
    dumped = req.model_dump_json()
    assert "NovelConverterのOCRとTTS統合を改善したい" in dumped


def test_atlas_autopilot_task_creation() -> None:
    task = AtlasAutopilotTask(task_id="t1", title="Plan", description="preview")
    assert task.task_id == "t1"


def test_atlas_autopilot_plan_multiple_tasks_and_json_dump() -> None:
    plan = AtlasAutopilotPlan(
        autopilot_id="auto_test_2",
        user_goal="大きめの改修を進めたい",
        interpreted_goal="preview",
        tasks=[
            AtlasAutopilotTask(task_id="t1", title="A"),
            AtlasAutopilotTask(task_id="t2", title="B", depends_on=["t1"]),
        ],
        safety_constraints=["Preview only"],
    )
    assert len(plan.tasks) == 2
    assert "t2" in plan.model_dump_json()
