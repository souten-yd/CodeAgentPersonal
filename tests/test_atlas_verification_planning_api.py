from fastapi.testclient import TestClient
from app.server import create_app


def test_endpoint_200(tmp_path):
    app = create_app(); app.state.atlas_ca_data_root = tmp_path
    c = TestClient(app)
    r = c.post('/api/atlas/repo-context/verification-plan', json={"project_path": str(tmp_path)})
    assert r.status_code == 200
    body = r.json()
    assert body['metadata']['executed'] is False
    assert body['metadata']['shell_executed'] is False
    assert body['metadata']['remote_git_executed'] is False
    assert body['metadata']['auto_verification_triggered'] is False
    assert body['metadata']['auto_test_execution_triggered'] is False
    assert body['status'] in {'missing', 'partial', 'available'}


def test_invalid_project_file_400(tmp_path):
    app=create_app(); app.state.atlas_ca_data_root=tmp_path; c=TestClient(app)
    f=tmp_path/'x.txt'; f.write_text('x')
    assert c.post('/api/atlas/repo-context/verification-plan', json={'project_path': str(f)}).status_code==400


def test_missing_index_returns_200_non_blocking(tmp_path):
    app = create_app()
    app.state.atlas_ca_data_root = tmp_path
    c = TestClient(app)
    repo = tmp_path / "repo"
    repo.mkdir()
    r = c.post('/api/atlas/repo-context/verification-plan', json={'project_path': str(repo)})
    assert r.status_code == 200
    assert r.json()['status'] in {'missing', 'partial'}
