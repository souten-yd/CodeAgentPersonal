from fastapi.testclient import TestClient
from main import app

def test_api_prepare_next_action():
    c=TestClient(app)
    r=c.post('/api/atlas/next-action-orchestrator/prepare', json={'pool_id':'default_pool'})
    assert r.status_code in (200,404)

def test_requested_next_action_allowlist():
    c=TestClient(app)
    r=c.post('/api/atlas/next-action-orchestrator/prepare', json={'pool_id':'x','requested_next_action':'xxx'})
    assert r.status_code==400
