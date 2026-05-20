from pathlib import Path
from fastapi.testclient import TestClient
from app.server import create_app


def test_context_refresh_v2_api_ok_and_data_root(tmp_path: Path):
    app = create_app(); app.state.atlas_ca_data_root = tmp_path
    c = TestClient(app)
    res = c.post('/api/atlas/context-refresh/v2', json={"project_path": str(tmp_path), "plan_pool": {"items": []}})
    assert res.status_code == 200
    d = res.json()
    assert 'status' in d and 'metadata' in d and d['metadata']['executed'] is False


def test_context_refresh_v2_api_rejects_file(tmp_path: Path):
    app = create_app(); app.state.atlas_ca_data_root = tmp_path
    f = tmp_path / 'x.txt'; f.write_text('x')
    c = TestClient(app)
    res = c.post('/api/atlas/context-refresh/v2', json={"project_path": str(f)})
    assert res.status_code == 400
