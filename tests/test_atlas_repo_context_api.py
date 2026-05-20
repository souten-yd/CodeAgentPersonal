from fastapi.testclient import TestClient
from app.server import create_app


def test_repo_context_policies():
    c = TestClient(create_app())
    r = c.get('/api/atlas/repo-context/policies')
    assert r.status_code == 200


def test_repo_context_snapshot_api():
    c = TestClient(create_app())
    r = c.post('/api/atlas/repo-context/snapshot', json={})
    assert r.status_code == 200
    assert r.json()['status'] == 'missing'
