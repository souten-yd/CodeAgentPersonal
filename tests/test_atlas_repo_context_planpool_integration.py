from fastapi.testclient import TestClient
from app.server import create_app


def test_create_plan_pool_succeeds_when_repo_index_missing():
    c = TestClient(create_app())
    r = c.post('/api/atlas/plan-pools', json={'input': 'x', 'project_path': '/tmp/not-found-repo'})
    assert r.status_code == 200
    assert r.json()['status'] == 'ready'


def test_create_plan_pool_repo_context_disabled(tmp_path):
    app = create_app()
    app.state.atlas_ca_data_root = tmp_path
    c = TestClient(app)
    project = tmp_path / "repo"
    project.mkdir()
    r = c.post('/api/atlas/plan-pools', json={'input': 'x', 'project_path': str(project), 'enable_repo_context': False})
    assert r.status_code == 200
    repo_context = r.json().get('metadata', {}).get('repo_context')
    assert repo_context is None or repo_context.get('status') == 'disabled'
