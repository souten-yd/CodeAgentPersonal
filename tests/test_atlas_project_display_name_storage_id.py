from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.atlas_projects import router


def _client(tmp_path: Path) -> TestClient:
    app = FastAPI()
    app.state.atlas_ca_data_dir = str(tmp_path)
    app.include_router(router)
    return TestClient(app)


def test_rename_changes_display_name_only_and_keeps_storage_id(tmp_path: Path) -> None:
    c = _client(tmp_path)
    created = c.post("/api/atlas/projects", json={}).json()
    storage_id = created["name"]
    assert storage_id.startswith("untitled-")

    c.post(
        f"/api/atlas/projects/{storage_id}/conversation",
        json={"role": "user", "text": "build game", "meta": {"active_pool_id": "pool_1"}},
    )
    work_file = tmp_path / "atlas" / "projects" / storage_id / "work" / "game.txt"
    work_file.write_text("ok\n", encoding="utf-8")
    workspace_file = tmp_path / "atlas" / "workspaces" / storage_id / "plan_pools" / "p.json"
    workspace_file.parent.mkdir(parents=True, exist_ok=True)
    workspace_file.write_text("{}", encoding="utf-8")

    renamed = c.post(f"/api/atlas/projects/{storage_id}/rename", json={"new_name": "インベーダーゲームを作って その"})
    assert renamed.status_code == 200
    body = renamed.json()

    assert body["name"] == storage_id
    assert body["display_name"] == "インベーダーゲームを作って-その"
    assert body["workspace_id"] == storage_id
    assert Path(body["project_path"]).parts[-2:] == (storage_id, "work")
    assert body["provisional"] is False
    assert work_file.exists()
    assert workspace_file.exists()

    conv = c.get(f"/api/atlas/projects/{storage_id}/conversation").json()
    assert conv["meta"]["active_pool_id"] == "pool_1"
    assert conv["meta"]["display_name"] == "インベーダーゲームを作って-その"
