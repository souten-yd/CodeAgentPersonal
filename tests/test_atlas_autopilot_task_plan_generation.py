from pathlib import Path

from agent.atlas_autopilot import AtlasAutopilot
from agent.atlas_autopilot_schema import AtlasAutopilotRequest


class FakePlanningRunner:
    def __init__(self):
        self.calls = []

    def run(self, **kwargs):
        self.calls.append(kwargs)
        assert kwargs["execution_mode"] == "plan_only"
        return {
            "status": "planned",
            "requirement_id": "req_1",
            "plan_id": "plan_1",
            "message": "Plan generated",
            "plan": {"plan_id": "plan_1"},
            "review_result": {"overall_risk": "low"},
            "warnings": [],
        }


def test_generate_plan_for_task_is_plan_only_and_no_file_changes(tmp_path: Path) -> None:
    runner = FakePlanningRunner()
    autopilot = AtlasAutopilot(ca_data_dir=str(tmp_path), planning_runner=runner)
    req = AtlasAutopilotRequest(autopilot_id="auto_plan_1", user_goal="goal", project_path=str(tmp_path))
    before = sorted(p.name for p in tmp_path.iterdir())
    preview = autopilot.start_preview(req)
    task_id = preview["tasks"][0]["task_id"]

    out = autopilot.generate_plan_for_task(autopilot_id=req.autopilot_id, task_id=task_id, project_path=str(tmp_path))

    assert runner.calls
    assert runner.calls[0]["execution_mode"] == "plan_only"
    assert out["status"] == "task_plan_ready"
    assert out["plan_id"] == "plan_1"
    assert out["requirement_id"] == "req_1"
    task = out["task"]
    assert task["linked_plan_id"] == "plan_1"
    assert task["linked_requirement_id"] == "req_1"
    after = sorted(p.name for p in tmp_path.iterdir())
    assert before == after
