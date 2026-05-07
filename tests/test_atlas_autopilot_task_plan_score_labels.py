from pathlib import Path

from agent.atlas_autopilot import AtlasAutopilot
from agent.atlas_autopilot_schema import AtlasAutopilotRequest
from agent.task_planning_runner import TaskPlanningRunner


def test_autopilot_generate_plan_accepts_requirement_score_labels(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    ca_data_dir = tmp_path / "ca_data"

    def fake_llm(_prompt: str, _input: str):
        return {
            "interpreted_goal": "test goal",
            "functional_requirements": ["prepare a safe plan"],
            "done_definition": ["plan is ready"],
            "requirement_completeness_score": "high",
            "category_scores": {
                "goal": "high",
                "scope": "medium",
                "functional_requirements": "70%",
                "non_functional_requirements": "0.7/1.0",
                "constraints": 70,
                "done_definition": "low",
            },
        }

    runner = TaskPlanningRunner(ca_data_dir=str(ca_data_dir), llm_json_fn=fake_llm)
    autopilot = AtlasAutopilot(ca_data_dir=str(ca_data_dir), planning_runner=runner, llm_json_fn=fake_llm)
    request = AtlasAutopilotRequest(
        autopilot_id="auto_score_labels",
        user_goal="Generate a plan with label scores",
        project_path=str(project_dir),
    )
    before_project_files = sorted(p.relative_to(project_dir) for p in project_dir.rglob("*"))
    preview = autopilot.start_preview(request)
    task_id = preview["tasks"][0]["task_id"]

    out = autopilot.generate_plan_for_task(
        autopilot_id=request.autopilot_id,
        task_id=task_id,
        project_path=str(project_dir),
        planning_mode="standard",
        requirement_mode="ask_when_needed",
    )

    assert out["status"] == "task_plan_ready"
    assert out["planning_result"]["execution_mode"] == "plan_only"
    assert out["planning_result"]["requirement"]["category_scores"]["goal"] == 0.85
    assert out["planning_result"]["requirement"]["requirement_completeness_score"] == 0.85
    after_project_files = sorted(p.relative_to(project_dir) for p in project_dir.rglob("*"))
    assert before_project_files == after_project_files
