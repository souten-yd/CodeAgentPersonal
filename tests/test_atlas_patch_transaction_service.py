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
from app.atlas.patch_transaction_apply import apply_patch_transaction_one_action


def _approved_apply_kwargs() -> dict[str, object]:
    return {
        "dry_run_gate_ready": True,
        "rollback_ready": True,
        "confirmation_token_present": True,
        "confirmation_text": "EXECUTE ONE ACTION",
        "approval_status": "approved",
        "explicit_decision": "approve",
    }


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


def test_apply_patch_transaction_one_action_requires_gates_and_does_not_auto_apply(tmp_path: Path) -> None:
    project = tmp_path / "project"
    data_root = tmp_path / "data"
    project.mkdir()
    target = project / "a.txt"
    target.write_text("old\n", encoding="utf-8")
    txn = create_patch_transaction(
        project_path=project,
        data_root=data_root,
        snapshot_id="snap_1",
        snapshot_manifest_path="/tmp/snap_manifest.json",
        proposed_files=[{"relative_path": "a.txt", "change_type": "modify"}],
        diff_text="diff --git a/a.txt b/a.txt\n--- a/a.txt\n+++ b/a.txt\n@@ -1 +1 @@\n-old\n+new\n",
        risk_class="low",
    )

    result = apply_patch_transaction_one_action(manifest_path=txn["manifest_path"], data_root=data_root, project_path=project)

    assert result["status"] == "blocked"
    assert "dry_run_gate_ready_required" in result["blocked_reasons"]
    assert "explicit_human_approval_required" in result["blocked_reasons"]
    assert target.read_text(encoding="utf-8") == "old\n"
    assert result["automatic_apply_enabled"] is False
    assert result["automatic_rollback_enabled"] is False
    assert result["autonomous_execution_enabled"] is False


def test_apply_patch_transaction_one_action_applies_single_approved_low_risk_patch(tmp_path: Path) -> None:
    project = tmp_path / "project"
    data_root = tmp_path / "data"
    project.mkdir()
    target = project / "a.txt"
    target.write_text("old\n", encoding="utf-8")
    txn = create_patch_transaction(
        project_path=project,
        data_root=data_root,
        snapshot_id="snap_1",
        snapshot_manifest_path="/tmp/snap_manifest.json",
        proposed_files=[{"relative_path": "a.txt", "change_type": "modify"}],
        diff_text="diff --git a/a.txt b/a.txt\n--- a/a.txt\n+++ b/a.txt\n@@ -1 +1 @@\n-old\n+new\n",
        risk_class="low",
    )

    result = apply_patch_transaction_one_action(
        manifest_path=txn["manifest_path"],
        data_root=data_root,
        project_path=project,
        **_approved_apply_kwargs(),
    )

    assert result["status"] == "applied"
    assert result["changed_files"] == ["a.txt"]
    assert result["actual_file_changed"] is True
    assert result["automatic_apply_enabled"] is False
    assert result["automatic_rollback_enabled"] is False
    assert result["autonomous_execution_enabled"] is False
    assert target.read_text(encoding="utf-8") == "new\n"
    apply_result_path = Path(result["apply_result_path"])
    assert apply_result_path.exists()
    assert apply_result_path.is_relative_to(Path(txn["transaction_dir"]))
    saved = json.loads(apply_result_path.read_text(encoding="utf-8"))
    assert saved["status"] == "applied"


def test_apply_patch_transaction_one_action_blocks_multiple_or_non_low_risk(tmp_path: Path) -> None:
    project = tmp_path / "project"
    data_root = tmp_path / "data"
    project.mkdir()
    (project / "a.txt").write_text("old\n", encoding="utf-8")
    (project / "b.txt").write_text("old\n", encoding="utf-8")
    multi = create_patch_transaction(
        project_path=project,
        data_root=data_root,
        snapshot_id="snap_1",
        snapshot_manifest_path="/tmp/snap_manifest.json",
        proposed_files=[
            {"relative_path": "a.txt", "change_type": "modify"},
            {"relative_path": "b.txt", "change_type": "modify"},
        ],
        diff_text="diff --git a/a.txt b/a.txt\n--- a/a.txt\n+++ b/a.txt\n@@ -1 +1 @@\n-old\n+new\n",
        risk_class="low",
    )
    medium = create_patch_transaction(
        project_path=project,
        data_root=data_root,
        snapshot_id="snap_2",
        snapshot_manifest_path="/tmp/snap_manifest.json",
        proposed_files=[{"relative_path": "a.txt", "change_type": "modify"}],
        diff_text="diff --git a/a.txt b/a.txt\n--- a/a.txt\n+++ b/a.txt\n@@ -1 +1 @@\n-old\n+new\n",
        risk_class="medium",
    )

    multi_result = apply_patch_transaction_one_action(
        manifest_path=multi["manifest_path"], data_root=data_root, project_path=project, **_approved_apply_kwargs()
    )
    medium_result = apply_patch_transaction_one_action(
        manifest_path=medium["manifest_path"], data_root=data_root, project_path=project, **_approved_apply_kwargs()
    )

    assert multi_result["status"] == "blocked"
    assert "single_file_required" in multi_result["blocked_reasons"]
    assert medium_result["status"] == "blocked"
    assert "low_risk_required" in medium_result["blocked_reasons"]
    assert (project / "a.txt").read_text(encoding="utf-8") == "old\n"
    assert (project / "b.txt").read_text(encoding="utf-8") == "old\n"


def test_no_direct_ca_data_writes_in_patch_transaction_source() -> None:
    text = Path("app/atlas/patch_transaction.py").read_text(encoding="utf-8")
    assert 'Path("ca_data")' not in text
    apply_text = Path("app/atlas/patch_transaction_apply.py").read_text(encoding="utf-8")
    assert 'Path("ca_data")' not in apply_text
    assert "subprocess" not in apply_text
    assert "os.system" not in apply_text
