from pathlib import Path

from app.atlas.workspace_snapshot import (
    SCHEMA_VERSION,
    create_workspace_snapshot,
    plan_workspace_restore,
    read_workspace_snapshot_manifest,
    restore_workspace_snapshot,
)


def test_snapshot_create_and_manifest_and_excludes(tmp_path: Path) -> None:
    project = tmp_path / "project"
    data_root = tmp_path / "data_root"
    project.mkdir()
    (project / "a.txt").write_text("hello", encoding="utf-8")
    (project / ".git").mkdir()
    (project / ".git" / "config").write_text("x", encoding="utf-8")
    before = (project / "a.txt").read_text(encoding="utf-8")

    result = create_workspace_snapshot(project_path=project, data_root=data_root)
    assert Path(result["snapshot_dir"]).is_relative_to(data_root)
    manifest_path = Path(result["manifest_path"])
    assert manifest_path.exists()
    manifest = read_workspace_snapshot_manifest(manifest_path=manifest_path, data_root=data_root)["manifest"]
    assert manifest["schema_version"] == SCHEMA_VERSION
    assert manifest["snapshot_id"]
    assert manifest["project_path"] == str(project.resolve())
    assert manifest["data_root"] == str(data_root.resolve())
    assert manifest["files"][0]["sha256"]
    assert all(not f["relative_path"].startswith(".git") for f in manifest["files"])
    assert (project / "a.txt").read_text(encoding="utf-8") == before


def test_manifest_rejects_unsafe_paths(tmp_path: Path) -> None:
    project = tmp_path / "p"
    data_root = tmp_path / "d"
    project.mkdir()
    (project / "x.txt").write_text("1", encoding="utf-8")
    result = create_workspace_snapshot(project_path=project, data_root=data_root)
    manifest_path = Path(result["manifest_path"])
    manifest = read_workspace_snapshot_manifest(manifest_path=manifest_path, data_root=data_root)["manifest"]
    manifest["files"][0]["relative_path"] = "../escape.txt"
    manifest_path.write_text(__import__("json").dumps(manifest), encoding="utf-8")
    out = restore_workspace_snapshot(manifest_path=manifest_path, data_root=data_root, project_path=project, confirm_restore=True)
    assert out["skipped_count"] >= 1


def test_plan_is_read_only_and_restore_requires_confirm(tmp_path: Path) -> None:
    project = tmp_path / "p2"
    data_root = tmp_path / "d2"
    project.mkdir()
    f = project / "a.txt"
    f.write_text("one", encoding="utf-8")
    result = create_workspace_snapshot(project_path=project, data_root=data_root)
    f.write_text("two", encoding="utf-8")
    plan = plan_workspace_restore(manifest_path=result["manifest_path"], data_root=data_root, project_path=project)
    assert "a.txt" in plan["files_changed_since_snapshot"]
    assert f.read_text(encoding="utf-8") == "two"

    blocked = restore_workspace_snapshot(manifest_path=result["manifest_path"], data_root=data_root, project_path=project, confirm_restore=False)
    assert blocked["status"] == "blocked"
    assert f.read_text(encoding="utf-8") == "two"

    restored = restore_workspace_snapshot(manifest_path=result["manifest_path"], data_root=data_root, project_path=project, confirm_restore=True)
    assert restored["status"] == "restored"
    assert f.read_text(encoding="utf-8") == "one"
    assert Path(restored["report_path"]).is_relative_to(data_root)


def test_no_direct_ca_data_writes_in_service_source() -> None:
    text = Path("app/atlas/workspace_snapshot.py").read_text(encoding="utf-8")
    assert 'Path("ca_data")' not in text
