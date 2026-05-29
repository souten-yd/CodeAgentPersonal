from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.atlas_projects import router
from agent.atlas_conversation_store import AtlasConversationStore


def _client(tmp_path: Path) -> TestClient:
    app = FastAPI()
    app.state.atlas_ca_data_dir = str(tmp_path)
    app.include_router(router)
    return TestClient(app)


def test_create_provisional_then_rename_and_persist(tmp_path: Path) -> None:
    c = _client(tmp_path)

    created = c.post("/api/atlas/projects", json={}).json()
    assert created["provisional"] is True
    prov = created["name"]
    assert prov.startswith("untitled-")

    # transcript persists server-side and survives rename
    c.post(f"/api/atlas/projects/{prov}/conversation", json={"role": "user", "text": "build a todo app", "meta": {"active_pool_id": "pool_abc"}})

    renamed = c.post(f"/api/atlas/projects/{prov}/rename", json={"new_name": "Build A Todo App!!"})
    assert renamed.status_code == 200
    new = renamed.json()["name"]
    assert new == "build-a-todo-app"
    assert renamed.json()["provisional"] is False

    conv = c.get(f"/api/atlas/projects/{new}/conversation").json()
    assert len(conv["messages"]) == 1
    assert conv["messages"][0]["text"] == "build a todo app"
    assert conv["meta"]["active_pool_id"] == "pool_abc"


def test_rename_conflict_returns_409(tmp_path: Path) -> None:
    c = _client(tmp_path)
    a = c.post("/api/atlas/projects", json={"name": "alpha"}).json()["name"]
    c.post("/api/atlas/projects", json={"name": "beta"})
    r = c.post(f"/api/atlas/projects/{a}/rename", json={"new_name": "beta"})
    assert r.status_code == 409


def test_download_includes_work_and_workspace(tmp_path: Path) -> None:
    import io
    import zipfile

    c = _client(tmp_path)
    name = c.post("/api/atlas/projects", json={"name": "demo"}).json()["name"]
    # drop a file into the working dir and an artifact into the atlas workspace
    (tmp_path / "atlas" / "projects" / name / "work" / "main.py").write_text("print(1)\n", encoding="utf-8")
    ws = tmp_path / "atlas" / "workspaces" / name / "plan_pools"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "p.json").write_text("{}", encoding="utf-8")

    dl = c.get(f"/api/atlas/projects/{name}/download")
    assert dl.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(dl.content)).namelist()
    assert any(n.endswith("work/main.py") for n in names)
    assert any("atlas_workspace/plan_pools/p.json" in n for n in names)


def test_delete_removes_project_and_workspace(tmp_path: Path) -> None:
    c = _client(tmp_path)
    name = c.post("/api/atlas/projects", json={"name": "gone"}).json()["name"]
    assert c.delete(f"/api/atlas/projects/{name}").status_code == 200
    assert c.get("/api/atlas/projects").json()["projects"] == []


def test_path_traversal_rejected(tmp_path: Path) -> None:
    c = _client(tmp_path)
    r = c.delete("/api/atlas/projects/..%2f..%2fetc")
    assert r.status_code in (400, 404)


def test_conversation_store_meta_roundtrip(tmp_path: Path) -> None:
    store = AtlasConversationStore(tmp_path, "ws1")
    store.append("user", "hello")
    store.append("atlas", "hi", meta={"active_pool_id": "pool_z"})
    assert [m["role"] for m in store.list()] == ["user", "atlas"]
    assert store.read_meta()["active_pool_id"] == "pool_z"
