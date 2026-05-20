from fastapi.testclient import TestClient
from app.server import create_app


def test_create_plan_pool_succeeds_when_repo_index_missing():
    c = TestClient(create_app())
    r = c.post('/api/atlas/plan-pools', json={'input': 'x', 'project_path': '/tmp/not-found-repo'})
    assert r.status_code == 200
    assert r.json()['status'] == 'ready'
