import json
from pathlib import Path

from app.atlas.patch_transaction import (
    SCHEMA_VERSION,
    build_latest_patch_transaction_workflow_metadata,
    create_patch_transaction,
    read_patch_transaction_manifest,
    summarize_patch_transaction,
    validate_patch_transaction,
)


def test_create_patch_transaction_writes_manifest_and_diff_under_data_root(tmp_path: Path) -> None:
    project = tmp_path / "project"
    data_root = tmp_path / "data"
    project.mkdir()
    (project / "a.txt").write_text("before", encoding="utf-8")
    before = (project / "a.txt").read_text(encoding="utf-8")

    res = create_patch_transaction(
        project_path=project,
        data_root=data_root,
        snapshot_id="snap_1",
        snapshot_manifest_path="/tmp/snap_manifest.json",
        proposed_files=[{"relative_path": "a.txt", "change_type": "modify"}],
        diff_text="diff --git a/a.txt b/a.txt\n--- a/a.txt\n+++ b/a.txt\n",
    )
    tx_dir = Path(res["transaction_dir"])
    assert tx_dir.is_relative_to(data_root)
    manifest_path = Path(res["manifest_path"])
    assert manifest_path.exists()
    manifest = read_patch_transaction_manifest(manifest_path=manifest_path, data_root=data_root)["manifest"]
    assert manifest["schema_version"] == SCHEMA_VERSION
    assert manifest["transaction_id"]
    assert manifest["project_path"] == str(project.resolve())
    assert manifest["data_root"] == str(data_root.resolve())
    assert manifest["proposed_files"]
    assert manifest["diff_summary"]["total_files"] >= 1
    assert manifest["rollback_metadata"]["rollback_strategy"] == "restore_snapshot_manual"
    assert manifest["apply_supported"] is False
    assert Path(manifest["diff_text_path"]).exists()
    assert Path(manifest["diff_text_path"]).is_relative_to(tx_dir)
    assert (project / "a.txt").read_text(encoding="utf-8") == before


def test_invalid_paths_marked_invalid(tmp_path: Path) -> None:
    project = tmp_path / "project"
    data_root = tmp_path / "data"
    project.mkdir()

    res = create_patch_transaction(
        project_path=project,
        data_root=data_root,
        proposed_files=[
            {"relative_path": "/abs.txt", "change_type": "modify"},
            {"relative_path": "../escape.txt", "change_type": "modify"},
        ],
        diff_files=[{"relative_path": "../bad.diffpath", "change_type": "unknown"}],
    )
    manifest = read_patch_transaction_manifest(manifest_path=res["manifest_path"], data_root=data_root)["manifest"]
    assert any(not e["path_valid"] for e in manifest["proposed_files"])


def test_validate_and_summary_read_only_and_flags(tmp_path: Path) -> None:
    project = tmp_path / "project"
    data_root = tmp_path / "data"
    project.mkdir()
    file = project / "a.txt"
    file.write_text("x", encoding="utf-8")
    before_mtime = file.stat().st_mtime_ns

    res = create_patch_transaction(
        project_path=project,
        data_root=data_root,
        proposed_files=[{"relative_path": "a.txt", "change_type": "modify"}],
    )
    validation = validate_patch_transaction(manifest_path=res["manifest_path"], data_root=data_root)
    assert validation["status"] == "validated"
    assert validation["apply_supported"] is False
    assert validation["automatic_apply_enabled"] is False
    assert validation["automatic_rollback_enabled"] is False
    assert file.stat().st_mtime_ns == before_mtime

    manifest = read_patch_transaction_manifest(manifest_path=res["manifest_path"], data_root=data_root)["manifest"]
    summary = summarize_patch_transaction(manifest, validation)
    assert summary["transaction_id"] == manifest["transaction_id"]
    assert summary["apply_supported"] is False


def test_latest_patch_transaction_workflow_metadata_is_read_only_preview(tmp_path: Path) -> None:
    project = tmp_path / "project"
    data_root = tmp_path / "data"
    project.mkdir()
    (project / "a.txt").write_text("x", encoding="utf-8")
    txn = create_patch_transaction(
        project_path=project,
        data_root=data_root,
        snapshot_id="snap_1",
        proposed_files=[{"relative_path": "a.txt", "change_type": "modify"}],
        risk_class="low",
    )

    metadata = build_latest_patch_transaction_workflow_metadata(data_root=data_root, project_path=project)

    assert metadata["patch_transaction_available"] is True
    assert metadata["latest_patch_transaction_id"] == txn["transaction_id"]
    assert metadata["patch_candidate_count"] == 1
    assert metadata["patch_transaction_source"] == "latest_patch_transaction_manifest"
    assert metadata["patch_transaction_risk_class"] == "low"
    assert metadata["patch_transaction_apply_supported"] is False
    assert metadata["patch_transaction_automatic_apply_enabled"] is False
    assert metadata["patch_transaction_automatic_rollback_enabled"] is False


def test_latest_patch_transaction_workflow_metadata_empty_state(tmp_path: Path) -> None:
    metadata = build_latest_patch_transaction_workflow_metadata(data_root=tmp_path)
    assert metadata["patch_transaction_available"] is False
    assert metadata["latest_patch_transaction_id"] is None
    assert metadata["patch_candidate_count"] == 0
    assert metadata["patch_transaction_source"] == "no_patch_transactions_found"


def test_no_direct_ca_data_writes_in_patch_transaction_source() -> None:
    text = Path("app/atlas/patch_transaction.py").read_text(encoding="utf-8")
    assert 'Path("ca_data")' not in text
