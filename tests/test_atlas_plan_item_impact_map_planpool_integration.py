from fastapi.testclient import TestClient
from app.server import create_app


def test_planpool_integration_has_metadata(tmp_path):
    c = TestClient(create_app())
    r = c.post('/api/atlas/plan-pools', json={"input": "do x", "project_path": str(tmp_path), "enable_repo_context": True})
    assert r.status_code == 200
    pool = r.json()["plan_pool"]
    assert "plan_item_impact_map" in pool.get("metadata", {})
    for item in pool.get("items", []):
        assert "impact_map" in item.get("metadata", {})


def test_disable_repo_context_no_map(tmp_path):
    c = TestClient(create_app())
    r = c.post('/api/atlas/plan-pools', json={"input": "do x", "project_path": str(tmp_path), "enable_repo_context": False})
    pool = r.json()["plan_pool"]
    assert "plan_item_impact_map" not in pool.get("metadata", {})
