from fastapi.testclient import TestClient
from app.server import create_app


def test_endpoint_200(tmp_path):
    c = TestClient(create_app())
    r = c.post('/api/atlas/repo-context/plan-item-impact-map', json={"project_path": str(tmp_path), "plan_pool": {"items": [{"item_id": "1"}]}})
    assert r.status_code == 200
    assert "impacts" in r.json()


def test_file_path_400(tmp_path):
    c = TestClient(create_app())
    f = tmp_path / 'x.txt'; f.write_text('x')
    r = c.post('/api/atlas/repo-context/plan-item-impact-map', json={"project_path": str(f), "plan_pool": {"items": [{"item_id": "1"}]}})
    assert r.status_code == 400
