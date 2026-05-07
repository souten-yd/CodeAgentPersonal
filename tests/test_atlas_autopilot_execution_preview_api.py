from fastapi.testclient import TestClient

import main


def test_execution_preview_api_states() -> None:
    client = TestClient(main.app)
    missing = client.post('/api/atlas/autopilot/missing/tasks/task_1/execution-preview', json={})
    assert missing.status_code == 200
    assert missing.json()["status"] == "not_found"

    preview = client.post('/api/atlas/autopilot/preview', json={"autopilot_id": "auto_api_ep", "user_goal": "Goal"})
    task_id = preview.json()["tasks"][0]["task_id"]
    no_plan = client.post(f'/api/atlas/autopilot/auto_api_ep/tasks/{task_id}/execution-preview', json={})
    assert no_plan.status_code == 200
    assert no_plan.json()["status"] == "plan_required"

    client.post(f'/api/atlas/autopilot/auto_api_ep/tasks/{task_id}/plan', json={})
    need_approval = client.post(f'/api/atlas/autopilot/auto_api_ep/tasks/{task_id}/execution-preview', json={})
    assert need_approval.status_code == 200
    assert need_approval.json()["status"] == "approval_required"
