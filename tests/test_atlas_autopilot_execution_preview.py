from agent.atlas_autopilot import AtlasAutopilot
from agent.atlas_autopilot_schema import AtlasAutopilotRequest


class FakePlanningRunner:
    def run(self, **kwargs):
        return {"status": "planned", "requirement_id": "req_1", "plan_id": "plan_1", "message": "ok"}


class FakePlanStorage:
    def __init__(self, approval=None):
        self.approval = approval

    def find_latest_approval_for_plan(self, plan_id: str):
        return self.approval


class FakePreview:
    def prepare_preview(self, **kwargs):
        return {"execution_preview_id": "execprev_1", "status": "execution_preview_ready", "summary": "Execution preview prepared. No files were changed.", "warnings": []}


def test_autopilot_execution_preview_gates_by_plan_and_approval(tmp_path):
    ap = AtlasAutopilot(ca_data_dir=str(tmp_path), planning_runner=FakePlanningRunner(), execution_preview=FakePreview(), plan_storage=FakePlanStorage(None))
    req = AtlasAutopilotRequest(autopilot_id="auto_ep", user_goal="goal")
    preview = ap.start_preview(req)
    task_id = preview["tasks"][0]["task_id"]

    out = ap.prepare_execution_preview_for_task(autopilot_id="auto_ep", task_id=task_id)
    assert out["status"] == "plan_required"

    ap.generate_plan_for_task(autopilot_id="auto_ep", task_id=task_id)
    out2 = ap.prepare_execution_preview_for_task(autopilot_id="auto_ep", task_id=task_id)
    assert out2["status"] == "approval_required"

    ap.plan_storage = FakePlanStorage({"approved_for_execution": True, "execution_ready": True})
    out3 = ap.prepare_execution_preview_for_task(autopilot_id="auto_ep", task_id=task_id)
    assert out3["status"] == "execution_preview_ready"
    assert out3["task"]["execution_preview_id"] == "execprev_1"
    state = ap.get_state("auto_ep")
    assert state["task_execution_preview_ids"][task_id] == "execprev_1"
