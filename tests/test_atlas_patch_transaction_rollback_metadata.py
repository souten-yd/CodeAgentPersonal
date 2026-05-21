from pathlib import Path

from app.atlas.patch_transaction import create_rollback_metadata


def test_create_rollback_metadata_contract_and_no_project_modification(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    marker = project / "x.txt"
    marker.write_text("unchanged", encoding="utf-8")
    before = marker.read_text(encoding="utf-8")

    meta = create_rollback_metadata(
        snapshot_id="snap_abc",
        snapshot_manifest_path="/tmp/snap.json",
        data_root=tmp_path / "data",
    )
    assert meta["rollback_strategy"] == "restore_snapshot_manual"
    assert meta["restore_manual_only"] is True
    assert meta["automatic_rollback_enabled"] is False
    assert meta["restore_plan_required"] is True
    assert meta["snapshot_id"] == "snap_abc"
    assert meta["snapshot_manifest_path"] == "/tmp/snap.json"
    assert marker.read_text(encoding="utf-8") == before


def test_missing_snapshot_metadata_has_warning_or_not_ready() -> None:
    meta = create_rollback_metadata(snapshot_id="", snapshot_manifest_path="", data_root="/tmp/data")
    assert meta["warnings"]
    assert meta["restore_supported"] is False
