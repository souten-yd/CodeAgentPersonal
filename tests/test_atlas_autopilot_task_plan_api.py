from fastapi.testclient import TestClient

import main


def test_autopilot_task_plan_api_not_found_and_ready() -> None:
    client = TestClient(main.app)
    missing = client.post('/api/atlas/autopilot/missing/tasks/task_1/plan', json={})
    assert missing.status_code == 200
    assert missing.json()["status"] in {"not_found", "planner_unavailable"}

    preview = client.post('/api/atlas/autopilot/preview', json={"autopilot_id": "auto_api_1", "user_goal": "Goal"})
    assert preview.status_code == 200
    task_id = preview.json()["tasks"][0]["task_id"]

    planned = client.post(f'/api/atlas/autopilot/auto_api_1/tasks/{task_id}/plan', json={"project_name": "CodeAgentPersonal", "planning_mode": "deep_nexus", "requirement_mode": "ask_when_needed", "use_nexus": True})
    assert planned.status_code == 200
    body = planned.json()
    assert body["status"] == "task_plan_ready"
    assert "plan_id" in body
    assert "requirement_id" in body
    assert "planning_result" in body
