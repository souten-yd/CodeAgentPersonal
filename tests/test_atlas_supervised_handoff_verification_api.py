from fastapi.testclient import TestClient
from app.server import create_app

def test_no_task_agent_routes():
    c=TestClient(create_app())
    assert c.get('/api/task/foo').status_code in (404,405)
    assert c.get('/api/agent/foo').status_code in (404,405)
