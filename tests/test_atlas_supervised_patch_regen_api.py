from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_no_task_agent_routes():
    assert client.get('/api/task/ping').status_code in (404,405)
    assert client.get('/api/agent/ping').status_code in (404,405)

def test_api_path_traversal_rejected():
    r = client.get('/api/atlas/patch-regen/results/../x/regen_abc')
    assert r.status_code in (400,404)

def test_invalid_ids_rejected():
    r = client.post('/api/atlas/patch-regen/run', json={"pool_id":"pool1","item_id":"i1","retry_run_id":"bad","target_files":["a.py"]})
    assert r.status_code == 400
