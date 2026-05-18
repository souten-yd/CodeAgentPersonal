from fastapi.testclient import TestClient
from app.server import create_app

def test_no_task_agent_routes():
    app=create_app(); c=TestClient(app)
    assert c.get('/api/task/x').status_code in {404,405}
    assert c.get('/api/agent/x').status_code in {404,405}
