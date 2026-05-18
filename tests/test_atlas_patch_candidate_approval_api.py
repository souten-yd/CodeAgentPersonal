from fastapi.testclient import TestClient
from main import app

client=TestClient(app)

def test_no_task_agent_routes():
    assert client.get('/api/task/ping').status_code in (404,405)

def test_api_path_traversal_rejected():
    assert client.get('/api/atlas/patch-candidate-approval/results/../x/approval_1').status_code in (400,404)
