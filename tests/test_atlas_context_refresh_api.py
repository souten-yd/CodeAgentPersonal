from fastapi.testclient import TestClient

from app.server import create_app


def test_api_run_context_refresh(tmp_path):
    app = create_app()
    client = TestClient(app)
    (tmp_path / "a.py").write_text("x=1\n", encoding="utf-8")
    res = client.post("/api/atlas/context-refresh/run", json={"pool_id": "api1", "trigger": "manual", "project_path": str(tmp_path), "changed_files": ["a.py"]})
    assert res.status_code == 200
    assert res.json().get("bundle_id")


def test_api_latest_context_refresh(tmp_path):
    app = create_app()
    client = TestClient(app)
    (tmp_path / "a.py").write_text("x=1\n", encoding="utf-8")
    client.post("/api/atlas/context-refresh/run", json={"pool_id": "api2", "trigger": "manual", "project_path": str(tmp_path), "changed_files": ["a.py"]})
    res = client.post("/api/atlas/context-refresh/latest", json={"pool_id": "api2"})
    assert res.status_code == 200


def test_bundle_api_rejects_path_traversal():
    app = create_app()
    client = TestClient(app)
    res = client.get("/api/atlas/context-refresh/bundles/../x/../y")
    assert res.status_code in {400, 404}


def test_latest_api_rejects_path_traversal():
    app = create_app()
    client = TestClient(app)
    res = client.post("/api/atlas/context-refresh/latest", json={"pool_id": "../x"})
    assert res.status_code == 400
