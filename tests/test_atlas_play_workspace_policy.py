import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.atlas_play import router as atlas_play_router
from app.atlas.play.file_service import (
    ABSENT_REVISION,
    PlayWorkspaceFileService,
    sha256_file,
)
from app.atlas.play.workspace_policy import (
    WorkspacePermission,
    decide_workspace_access,
)


def _project(tmp_path: Path) -> Path:
    work = tmp_path / "atlas" / "projects" / "demo" / "work"
    work.mkdir(parents=True)
    return work


def _client(tmp_path: Path) -> TestClient:
    app = FastAPI()
    app.state.atlas_ca_data_root = str(tmp_path)
    app.include_router(atlas_play_router)
    return TestClient(app)


def _can_symlink(tmp_path: Path) -> bool:
    target = tmp_path / "target"
    link = tmp_path / "link"
    target.write_text("x", encoding="utf-8")
    try:
        link.symlink_to(target)
        return link.is_symlink()
    except OSError:
        return False


@pytest.mark.parametrize(
    "bad_path",
    [
        "../secret.txt",
        "%2e%2e/secret.txt",
        "safe/%252e%252e/secret.txt",
        "/tmp/secret.txt",
        "C:/temp/secret.txt",
        r"\\server\share\secret.txt",
        "safe//secret.txt",
    ],
)
def test_workspace_policy_rejects_escape_paths(tmp_path: Path, bad_path: str) -> None:
    work = _project(tmp_path)

    for permission in WorkspacePermission:
        decision = decide_workspace_access(
            project_root=work,
            relative_path=bad_path,
            permission=permission,
        )
        assert decision.allowed is False
        assert decision.reason in {
            "path_traversal_forbidden",
            "absolute_path_forbidden",
        }


def test_workspace_policy_keeps_permissions_independent_and_blocks_protected_dirs(tmp_path: Path) -> None:
    work = _project(tmp_path)
    (work / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (work / "node_modules").mkdir()
    (work / "node_modules" / "pkg.js").write_text("x", encoding="utf-8")

    read = decide_workspace_access(project_root=work, relative_path="app.py", permission=WorkspacePermission.READ)
    write = decide_workspace_access(project_root=work, relative_path="app.py", permission=WorkspacePermission.WRITE)
    execute = decide_workspace_access(project_root=work, relative_path="app.py", permission=WorkspacePermission.EXECUTE)
    serve = decide_workspace_access(project_root=work, relative_path="app.py", permission=WorkspacePermission.SERVE)
    assert {read.allowed, write.allowed, execute.allowed, serve.allowed} == {True}
    assert read.permission == WorkspacePermission.READ
    assert write.permission == WorkspacePermission.WRITE
    assert execute.permission == WorkspacePermission.EXECUTE
    assert serve.permission == WorkspacePermission.SERVE

    protected = decide_workspace_access(
        project_root=work,
        relative_path="node_modules/pkg.js",
        permission=WorkspacePermission.READ,
    )
    assert protected.allowed is False
    assert protected.reason == "protected_directory"
    assert protected.protected_directory == "node_modules"


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlink unsupported")
def test_workspace_policy_rejects_symlink_escape(tmp_path: Path) -> None:
    if not _can_symlink(tmp_path):
        pytest.skip("symlink creation unavailable")
    work = _project(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    (work / "linked").symlink_to(outside, target_is_directory=True)

    decision = decide_workspace_access(
        project_root=work,
        relative_path="linked/secret.txt",
        permission=WorkspacePermission.READ,
    )
    assert decision.allowed is False
    assert decision.reason in {"path_escape", "symlink_escape"}


def test_file_service_lists_reads_and_writes_with_revision_precondition(tmp_path: Path) -> None:
    work = _project(tmp_path)
    app_file = work / "app.py"
    app_file.write_text("print('old')\n", encoding="utf-8")
    service = PlayWorkspaceFileService(project_root=work)

    listed = service.list_files()
    assert listed["status"] == "ok"
    assert any(entry["relative_path"] == "app.py" for entry in listed["files"])

    read = service.read_file(relative_path="app.py")
    assert read["status"] == "ok"
    assert read["content"] == "print('old')\n"

    stale = service.write_file(
        relative_path="app.py",
        content="print('new')\n",
        expected_sha256="not-current",
    )
    assert stale["status"] == "conflict"
    assert stale["reason"] == "stale_write_conflict"
    assert app_file.read_text(encoding="utf-8") == "print('old')\n"

    written = service.write_file(
        relative_path="app.py",
        content="print('new')\n",
        expected_sha256=read["sha256"],
    )
    assert written["status"] == "written"
    assert app_file.read_text(encoding="utf-8") == "print('new')\n"

    created = service.write_file(
        relative_path="nested/new.txt",
        content="created\n",
        expected_sha256=ABSENT_REVISION,
    )
    assert created["status"] == "written"
    assert (work / "nested" / "new.txt").read_text(encoding="utf-8") == "created\n"


def test_file_service_blocks_binary_large_and_protected_files(tmp_path: Path) -> None:
    work = _project(tmp_path)
    (work / "image.bin").write_bytes(b"\x00\x01binary")
    (work / ".git").mkdir()
    (work / ".git" / "config").write_text("secret", encoding="utf-8")
    service = PlayWorkspaceFileService(project_root=work)
    service.limits.max_file_bytes = 8
    (work / "large.txt").write_text("x" * 9, encoding="utf-8")

    assert service.read_file(relative_path="image.bin")["reason"] == "binary_file"
    assert service.read_file(relative_path="large.txt")["reason"] == "file_too_large"
    assert service.read_file(relative_path=".git/config")["reason"] == "protected_directory"


def test_atlas_play_workspace_file_api_uses_project_work_root_and_conflict_status(tmp_path: Path) -> None:
    work = _project(tmp_path)
    file_path = work / "index.html"
    file_path.write_text("<h1>old</h1>\n", encoding="utf-8")
    client = _client(tmp_path)

    listed = client.post(
        "/api/atlas/play/workspace/files/list",
        json={"project_id": "demo", "directory": "."},
    )
    assert listed.status_code == 200
    assert any(entry["relative_path"] == "index.html" for entry in listed.json()["files"])

    read = client.post(
        "/api/atlas/play/workspace/files/read",
        json={"project_id": "demo", "relative_path": "index.html"},
    )
    assert read.status_code == 200
    digest = read.json()["sha256"]
    assert digest == sha256_file(file_path)

    conflict = client.post(
        "/api/atlas/play/workspace/files/write",
        json={
            "project_id": "demo",
            "relative_path": "index.html",
            "content": "<h1>new</h1>\n",
            "expected_sha256": "stale",
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["reason"] == "stale_write_conflict"

    written = client.post(
        "/api/atlas/play/workspace/files/write",
        json={
            "project_id": "demo",
            "relative_path": "index.html",
            "content": "<h1>new</h1>\n",
            "expected_sha256": digest,
        },
    )
    assert written.status_code == 200
    assert file_path.read_text(encoding="utf-8") == "<h1>new</h1>\n"

    escape = client.post(
        "/api/atlas/play/workspace/files/read",
        json={"project_id": "demo", "relative_path": "%2e%2e/secret.txt"},
    )
    assert escape.status_code == 400
    assert escape.json()["detail"]["reason"] == "path_traversal_forbidden"
