from pathlib import Path
import os
import pytest

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


def _can_symlink(tmp_path: Path) -> bool:
    probe_target = tmp_path / "probe_target.txt"
    probe_link = tmp_path / "probe_link.txt"
    probe_target.write_text("ok", encoding="utf-8")
    try:
        probe_link.symlink_to(probe_target)
        return probe_link.is_symlink()
    except OSError:
        return False


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlink unsupported")
def test_snapshot_skips_symlink_to_outside_project(tmp_path: Path) -> None:
    if not _can_symlink(tmp_path):
        pytest.skip("symlink creation unavailable")
    project = tmp_path / "project"
    outside = tmp_path / "outside.txt"
    data_root = tmp_path / "data"
    project.mkdir()
    (project / "inside.txt").write_text("inside", encoding="utf-8")
    outside.write_text("outside-secret", encoding="utf-8")
    (project / "leak.txt").symlink_to(outside)
    result = create_workspace_snapshot(project_path=project, data_root=data_root)
    manifest = read_workspace_snapshot_manifest(manifest_path=result["manifest_path"], data_root=data_root)["manifest"]
    assert not any(f["relative_path"] == "leak.txt" for f in manifest["files"])
    assert any(s["relative_path"] == "leak.txt" and s["reason"] in {"symlink_skipped", "symlink_escape"} for s in manifest["skipped_files"])


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlink unsupported")
def test_snapshot_skips_internal_symlink_but_includes_real_file(tmp_path: Path) -> None:
    if not _can_symlink(tmp_path):
        pytest.skip("symlink creation unavailable")
    project = tmp_path / "project"
    data_root = tmp_path / "data"
    project.mkdir()
    (project / "real.txt").write_text("real", encoding="utf-8")
    (project / "link.txt").symlink_to(project / "real.txt")
    result = create_workspace_snapshot(project_path=project, data_root=data_root)
    manifest = read_workspace_snapshot_manifest(manifest_path=result["manifest_path"], data_root=data_root)["manifest"]
    assert any(f["relative_path"] == "real.txt" for f in manifest["files"])
    assert not any(f["relative_path"] == "link.txt" for f in manifest["files"])
    assert any(s["relative_path"] == "link.txt" and s["reason"] == "symlink_skipped" for s in manifest["skipped_files"])


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlink unsupported")
def test_include_path_symlink_is_skipped(tmp_path: Path) -> None:
    if not _can_symlink(tmp_path):
        pytest.skip("symlink creation unavailable")
    project = tmp_path / "project"
    outside = tmp_path / "outside"
    data_root = tmp_path / "data"
    project.mkdir()
    outside.mkdir()
    (outside / "x.txt").write_text("x", encoding="utf-8")
    (project / "linked_dir").symlink_to(outside, target_is_directory=True)
    result = create_workspace_snapshot(project_path=project, data_root=data_root, include_paths=["linked_dir"])
    assert any(("include_path_symlink_skipped" in w) or ("include_path_escape" in w) for w in result["warnings"])
    assert any(s["reason"] in {"symlink_skipped", "symlink_escape"} for s in result["skipped_files"])


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlink unsupported")
def test_restore_skips_symlink_restore_source(tmp_path: Path) -> None:
    if not _can_symlink(tmp_path):
        pytest.skip("symlink creation unavailable")
    project = tmp_path / "project"
    data_root = tmp_path / "data"
    outside = tmp_path / "outside.txt"
    project.mkdir()
    (project / "a.txt").write_text("one", encoding="utf-8")
    outside.write_text("outside", encoding="utf-8")
    snap = create_workspace_snapshot(project_path=project, data_root=data_root)
    manifest = read_workspace_snapshot_manifest(manifest_path=snap["manifest_path"], data_root=data_root)["manifest"]
    snap_file = Path(snap["snapshot_dir"]) / manifest["files"][0]["snapshot_relative_path"]
    snap_file.unlink()
    snap_file.symlink_to(outside)
    (project / "a.txt").write_text("changed", encoding="utf-8")
    out = restore_workspace_snapshot(manifest_path=snap["manifest_path"], data_root=data_root, project_path=project, confirm_restore=True)
    assert "symlink_restore_source_skipped" in "\n".join(out["warnings"])
    assert (project / "a.txt").read_text(encoding="utf-8") == "changed"


def test_snapshot_relative_path_traversal_rejected(tmp_path: Path) -> None:
    project = tmp_path / "p3"
    data_root = tmp_path / "d3"
    project.mkdir()
    (project / "a.txt").write_text("x", encoding="utf-8")
    result = create_workspace_snapshot(project_path=project, data_root=data_root)
    manifest_path = Path(result["manifest_path"])
    manifest = read_workspace_snapshot_manifest(manifest_path=manifest_path, data_root=data_root)["manifest"]
    manifest["files"][0]["snapshot_relative_path"] = "../escape"
    manifest_path.write_text(__import__("json").dumps(manifest), encoding="utf-8")
    out = restore_workspace_snapshot(manifest_path=manifest_path, data_root=data_root, project_path=project, confirm_restore=True)
    assert out["skipped_count"] >= 1


def test_delete_missing_before_is_non_destructive(tmp_path: Path) -> None:
    project = tmp_path / "p4"
    data_root = tmp_path / "d4"
    project.mkdir()
    (project / "a.txt").write_text("one", encoding="utf-8")
    snap = create_workspace_snapshot(project_path=project, data_root=data_root)
    extra = project / "extra.txt"
    extra.write_text("extra", encoding="utf-8")
    plan = plan_workspace_restore(manifest_path=snap["manifest_path"], data_root=data_root, project_path=project, delete_missing_before=True)
    assert "extra.txt" in plan["files_missing_from_snapshot"]
    assert "delete_missing_before_plan_only" in plan["warnings"]
    out = restore_workspace_snapshot(manifest_path=snap["manifest_path"], data_root=data_root, project_path=project, confirm_restore=True, delete_missing_before=True)
    assert extra.exists()
    report = __import__("json").loads(Path(out["report_path"]).read_text(encoding="utf-8"))
    assert report["delete_missing_before_executed"] is False
