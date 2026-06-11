from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.portal import router as portal_router


def _client(tmp_path: Path) -> TestClient:
    app = FastAPI()
    app.state.atlas_ca_data_root = str(tmp_path)
    app.include_router(portal_router)
    return TestClient(app)


def test_browse_lists_dirs_and_zip_archives_only(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "pkg.portal.zip").write_bytes(b"PK\x03\x04zip")
    (tmp_path / "other.zip").write_bytes(b"PK\x03\x04zip")
    (tmp_path / "notes.txt").write_text("ignore me", encoding="utf-8")

    resp = _client(tmp_path).post("/api/portal/import/browse", json={"path": str(tmp_path)})
    assert resp.status_code == 200
    data = resp.json()
    names = {e["name"]: e for e in data["entries"]}

    assert "notes.txt" not in names  # non-archive files are hidden
    assert names["sub"]["is_dir"] is True
    assert names["pkg.portal.zip"]["is_zip"] is True
    assert names["other.zip"]["is_zip"] is True
    assert data["path"] == str(tmp_path.resolve())
    assert data["parent"] == str(tmp_path.resolve().parent)
    assert data["roots"]  # environment-appropriate quick roots are always provided
    assert data["platform"] in {"windows", "linux", "runpod"}
    assert data["error"] == ""


def test_browse_reports_missing_directory_without_raising(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    resp = _client(tmp_path).post("/api/portal/import/browse", json={"path": str(missing)})
    assert resp.status_code == 200
    assert resp.json()["error"] == "directory_not_found"


def test_browse_empty_path_uses_default_root(tmp_path: Path) -> None:
    resp = _client(tmp_path).post("/api/portal/import/browse", json={"path": ""})
    assert resp.status_code == 200
    data = resp.json()
    assert data["default_path"]
    assert data["path"]  # resolved to the default landing directory
