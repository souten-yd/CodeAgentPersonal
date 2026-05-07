from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.server import create_app
import main


def test_create_app_workspace_mount_serves_index_html(tmp_path):
    (tmp_path / "index.html").write_text(
        "<!doctype html><title>Workspace</title><main>factory workspace</main>\n",
        encoding="utf-8",
    )
    app = create_app(workspace_dir=tmp_path)
    client = TestClient(app)

    response = client.get("/workspace/")

    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "").lower()
    assert "factory workspace" in response.text


def test_create_app_without_workspace_dir_does_not_mount_workspace():
    app = create_app()
    client = TestClient(app)

    response = client.get("/workspace/")

    assert response.status_code == 404


def test_main_workspace_mount_serves_index_when_work_dir_has_index():
    index_path = Path(main.WORK_DIR) / "index.html"
    if not index_path.is_file():
        pytest.skip(f"{index_path} is not present")
    client = TestClient(main.app)

    response = client.get("/workspace/")

    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "").lower()
