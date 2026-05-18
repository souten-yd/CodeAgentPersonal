from fastapi.testclient import TestClient
from app.server import create_app


def test_api_path_traversal_rejected():
    c=TestClient(create_app())
    r=c.post('/api/atlas/patch-regen-recommendation/run', json={"pool_id":"../x","item_id":"i1","supervised_retry_run_id":"retryhandoff_x"})
    assert r.status_code==400


def test_no_task_agent_routes():
    c=TestClient(create_app())
    assert c.get('/api/task/x').status_code in (404,405)
    assert c.get('/api/agent/x').status_code in (404,405)
