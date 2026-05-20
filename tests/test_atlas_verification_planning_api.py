from fastapi.testclient import TestClient
from app.server import create_app


def test_endpoint_200(tmp_path):
    app = create_app(); app.state.atlas_ca_data_root = tmp_path
    c = TestClient(app)
    r = c.post('/api/atlas/repo-context/verification-plan', json={"project_path": str(tmp_path)})
    assert r.status_code == 200
    assert r.json()['metadata']['executed'] is False


def test_invalid_project_file_400(tmp_path):
    app=create_app(); app.state.atlas_ca_data_root=tmp_path; c=TestClient(app)
    f=tmp_path/'x.txt'; f.write_text('x')
    assert c.post('/api/atlas/repo-context/verification-plan', json={'project_path': str(f)}).status_code==400
