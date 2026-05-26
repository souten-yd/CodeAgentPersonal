import json
from pathlib import Path

import pytest

from recovery.recover import (
    build_recovery_manifest,
    hash_file_sha256,
    load_recovery_manifest,
    plan_release_pointer_switch,
    read_release_pointer,
    validate_recovery_manifest,
    write_recovery_manifest,
)


def test_build_recovery_manifest_ready_without_execution(tmp_path: Path) -> None:
    store = tmp_path / "checkpoint_store"
    reports = store / "reports"
    pointer = store / "current_release.json"

    manifest = build_recovery_manifest(
        checkpoint_store=store,
        release_pointer_path=pointer,
        recovery_reports_dir=reports,
        stable_release_id="stable_001",
        allowed_actions=["inspect", "validate_pointer", "plan_pointer_switch", "record_report"],
    )

    assert manifest["status"] == "ready"
    assert manifest["external_supervisor"] is True
    assert manifest["application_runtime_independent"] is True
    assert manifest["manual_operation_required"] is True
    assert manifest["plan_release_pointer_switch_allowed"] is True
    assert manifest["record_recovery_report_allowed"] is True
    assert manifest["command_execution_enabled"] is False
    assert manifest["restore_execution_enabled"] is False
    assert manifest["pointer_switch_execution_enabled"] is False
    assert manifest["execution_performed"] is False
    assert manifest["pointer_switched"] is False
    assert manifest["mutation_performed"] is False


def test_build_recovery_manifest_blocks_invalid_paths_and_actions(tmp_path: Path) -> None:
    store = tmp_path / "checkpoint_store"
    manifest = build_recovery_manifest(
        checkpoint_store=store,
        release_pointer_path=tmp_path / "wrong_name.json",
        recovery_reports_dir=tmp_path / "reports_outside",
        stable_release_id="",
        allowed_actions=["inspect", "execute_shell"],
    )

    assert manifest["status"] == "blocked"
    assert "stable_release_id_required" in manifest["blocking_reasons"]
    assert "recovery_action_not_allowed" in manifest["blocking_reasons"]
    assert "release_pointer_filename_required" in manifest["blocking_reasons"]
    assert "release_pointer_must_be_in_checkpoint_store" in manifest["blocking_reasons"]
    assert "reports_dir_must_be_under_checkpoint_store" in manifest["blocking_reasons"]


def test_validate_recovery_manifest_rejects_execution_enablement(tmp_path: Path) -> None:
    store = tmp_path / "checkpoint_store"
    manifest = build_recovery_manifest(
        checkpoint_store=store,
        release_pointer_path=store / "current_release.json",
        recovery_reports_dir=store / "reports",
        stable_release_id="stable_001",
    )
    manifest["command_execution_enabled"] = True

    with pytest.raises(ValueError, match="command_execution_enabled"):
        validate_recovery_manifest(manifest)


def test_write_and_load_recovery_manifest(tmp_path: Path) -> None:
    store = tmp_path / "checkpoint_store"
    manifest = build_recovery_manifest(
        checkpoint_store=store,
        release_pointer_path=store / "current_release.json",
        recovery_reports_dir=store / "reports",
        stable_release_id="stable_001",
    )

    path = write_recovery_manifest(manifest=manifest, destination=store / "recovery_manifest.json")
    loaded = load_recovery_manifest(manifest_path=path)

    assert loaded["manifest_id"] == manifest["manifest_id"]
    assert loaded["stable_release_id"] == "stable_001"


def test_read_release_pointer_and_hash_file(tmp_path: Path) -> None:
    pointer = tmp_path / "current_release.json"
    pointer.write_text(json.dumps({"release_id": "stable_001"}), encoding="utf-8")
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("atlas", encoding="utf-8")

    assert read_release_pointer(pointer_path=pointer)["release_id"] == "stable_001"
    assert hash_file_sha256(artifact) == "d50e064c652f28c0c12625e58d90781660e303d5d4ad9c9369550a10238757be"


def test_plan_release_pointer_switch_is_plan_only(tmp_path: Path) -> None:
    store = tmp_path / "checkpoint_store"
    manifest = build_recovery_manifest(
        checkpoint_store=store,
        release_pointer_path=store / "current_release.json",
        recovery_reports_dir=store / "reports",
        stable_release_id="stable_001",
        allowed_actions=["inspect", "plan_pointer_switch"],
    )

    plan = plan_release_pointer_switch(manifest=manifest, target_release_id="stable_002")

    assert plan["status"] == "planned"
    assert plan["current_release_id"] == "stable_001"
    assert plan["target_release_id"] == "stable_002"
    assert plan["manual_operation_required"] is True
    assert plan["execution_performed"] is False
    assert plan["pointer_switched"] is False
    assert plan["mutation_performed"] is False


def test_recovery_supervisor_source_has_no_runtime_or_process_dependency() -> None:
    text = Path("recovery/recover.py").read_text(encoding="utf-8")
    forbidden = [
        "from app",
        "import app",
        "main.py",
        "FastAPI",
        "openai",
        "anthropic",
        "subprocess",
        "os.system",
        "requests",
    ]
    for needle in forbidden:
        assert needle not in text
