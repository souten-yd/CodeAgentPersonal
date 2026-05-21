from pathlib import Path

from app.atlas.patch_transaction import create_patch_transaction, read_patch_transaction_manifest
from app.atlas.risk_classification import classify_patch_transaction_risk


def test_patch_transaction_risk_integration_and_non_mutation(tmp_path: Path) -> None:
    project = tmp_path / "project"
    data_root = tmp_path / "data"
    project.mkdir()
    txn = create_patch_transaction(
        project_path=project,
        data_root=data_root,
        proposed_files=[{"relative_path": "docs/guide.md", "change_type": "modify"}],
    )
    manifest_path = txn["manifest_path"]
    before = Path(manifest_path).read_text(encoding="utf-8")
    risk = classify_patch_transaction_risk(data_root=data_root, transaction_manifest_path=manifest_path)
    rm = risk["manifest"]
    assert rm["transaction_id"] == txn["transaction_id"]
    assert rm["transaction_manifest_path"]
    assert rm["proposed_files"]
    assert rm["autonomous_allowed"] is False
    assert rm["automatic_apply_allowed"] is False
    assert rm["automatic_rollback_allowed"] is False
    assert Path(manifest_path).read_text(encoding="utf-8") == before


def test_strict_gate_from_transaction_and_missing_snapshot_warnings(tmp_path: Path) -> None:
    project = tmp_path / "project"
    data_root = tmp_path / "data"
    project.mkdir()
    txn = create_patch_transaction(
        project_path=project,
        data_root=data_root,
        proposed_files=[{"relative_path": "app/api/new_endpoint.py", "change_type": "modify"}],
        snapshot_id="",
        snapshot_manifest_path="",
    )
    risk = classify_patch_transaction_risk(data_root=data_root, transaction_id=txn["transaction_id"])
    assert risk["manifest"]["risk_level"] == "strict_gate"
    assert "snapshot_id_missing" in risk["manifest"]["warnings"]
    assert "snapshot_manifest_path_missing" in risk["manifest"]["warnings"]
