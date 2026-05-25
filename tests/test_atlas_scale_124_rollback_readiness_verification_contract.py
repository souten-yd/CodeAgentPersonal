import json
from pathlib import Path

import pytest

from app.atlas.level1_execution_artifact_capture import create_level1_execution_artifact_manifest
from app.atlas.level1_rollback_readiness_verification import (
    SCHEMA_VERSION,
    create_level1_rollback_readiness_verification_manifest,
    load_level1_rollback_readiness_verification_manifest,
    validate_level1_rollback_readiness_verification_manifest,
    write_level1_rollback_readiness_verification_manifest,
)
from app.atlas.level1_stop_kill_switch_runtime import create_level1_stop_kill_switch_runtime_manifest
from app.atlas.rollback_readiness_gate import create_rollback_readiness_record


def _rollback_ready(project: Path, data_root: Path) -> dict:
    record = create_rollback_readiness_record(
        data_root=data_root,
        project_path=project,
        risk_level="low",
        transaction_id="txn1",
        snapshot_id="snap1",
        restore_plan_status="valid",
        restore_supported=True,
        restore_manual_only=True,
        rollback_metadata_present=True,
        rollback_strategy="restore_snapshot_manual",
        snapshot_manifest_valid=True,
        snapshot_path_safety_valid=True,
        transaction_rollback_metadata_valid=True,
        dry_run_gate_id="gate1",
        dry_run_gate_ready=True,
        dry_run=True,
    )
    return record["manifest"]


def _stop_ready(project: Path, data_root: Path) -> dict:
    execution_artifact = create_level1_execution_artifact_manifest(
        workspace_id="ws_1",
        pool_id="pool_1",
        item_id="item_1",
        run_id="run_1",
        action_id="action_1",
        runner_id="disabled_runner_1",
        dry_run_artifact_id="dry_run_artifact_1",
        allowlist_id="allow_1",
        risk_level="low",
    )
    return create_level1_stop_kill_switch_runtime_manifest(
        project_path=project,
        data_root=data_root,
        workspace_id="ws_1",
        pool_id="pool_1",
        item_id="item_1",
        run_id="run_1",
        action_id="action_1",
        execution_artifact_manifest=execution_artifact,
        execution_artifact_manifest_path=str(data_root / "execution-artifact.json"),
    )


def test_scale_124_verifies_rollback_readiness_without_rollback_or_restore(tmp_path: Path) -> None:
    project = tmp_path / "project"
    data_root = tmp_path / "data"
    project.mkdir()
    manifest = create_level1_rollback_readiness_verification_manifest(
        project_path=project,
        data_root=data_root,
        workspace_id="ws_1",
        pool_id="pool_1",
        item_id="item_1",
        run_id="run_1",
        action_id="action_1",
        rollback_readiness_manifest=_rollback_ready(project, data_root),
        rollback_readiness_manifest_path=str(data_root / "rollback.json"),
        stop_runtime_manifest=_stop_ready(project, data_root),
        stop_runtime_manifest_path=str(data_root / "stop-runtime.json"),
    )

    assert manifest["schema_version"] == SCHEMA_VERSION
    assert manifest["runtime_level"] == "level_0_manual_only"
    assert manifest["verify_only"] is True
    assert manifest["rollback_readiness_verified"] is True
    assert manifest["rollback_ready"] is True
    assert manifest["restore_plan_valid"] is True
    assert manifest["snapshot_manifest_valid"] is True
    assert manifest["snapshot_path_safety_valid"] is True
    assert manifest["transaction_rollback_metadata_valid"] is True
    assert manifest["dry_run_gate_ready"] is True
    assert manifest["stop_runtime_integration_verified"] is True
    assert manifest["stop_blocks_continuation"] is True
    assert manifest["automatic_rollback_enabled"] is False
    assert manifest["automatic_restore_enabled"] is False
    assert manifest["automatic_execute_enabled"] is False
    assert manifest["automatic_verification_enabled"] is False
    assert manifest["automatic_safe_apply_enabled"] is False
    assert manifest["level1_execution_enabled"] is False
    assert manifest["autonomous_execution_enabled"] is False
    assert manifest["rollback_performed"] is False
    assert manifest["restore_performed"] is False
    assert manifest["mutation_performed"] is False
    assert manifest["verification_performed"] is False
    assert manifest["backend_authoritative"] is True
    assert manifest["vue_authoritative"] is False
    assert manifest["next_required_pr"] == "PR-ATLAS-SCALE-125"

    path = write_level1_rollback_readiness_verification_manifest(data_root=data_root, manifest=manifest)
    assert path.exists()
    assert path.is_relative_to(data_root)
    loaded = load_level1_rollback_readiness_verification_manifest(manifest_path=path, data_root=data_root)
    assert loaded["verification_id"] == manifest["verification_id"]


def test_scale_124_blocks_missing_or_invalid_evidence(tmp_path: Path) -> None:
    project = tmp_path / "project"
    data_root = tmp_path / "data"
    project.mkdir()
    rollback_manifest = _rollback_ready(project, data_root)
    rollback_manifest["restore_plan_status"] = "missing"
    manifest = create_level1_rollback_readiness_verification_manifest(
        project_path=project,
        data_root=data_root,
        rollback_readiness_manifest=rollback_manifest,
        stop_runtime_manifest={},
    )

    assert manifest["rollback_readiness_verified"] is False
    assert "restore_plan_valid_required" in manifest["blocking_reasons"]
    assert "stop_runtime_manifest_missing" in manifest["blocking_reasons"]
    assert manifest["automatic_rollback_enabled"] is False
    assert manifest["restore_performed"] is False


def test_scale_124_validation_rejects_execution_or_automatic_rollback(tmp_path: Path) -> None:
    project = tmp_path / "project"
    data_root = tmp_path / "data"
    project.mkdir()
    manifest = create_level1_rollback_readiness_verification_manifest(
        project_path=project,
        data_root=data_root,
        rollback_readiness_manifest=_rollback_ready(project, data_root),
        stop_runtime_manifest=_stop_ready(project, data_root),
    )
    manifest["automatic_rollback_enabled"] = True
    with pytest.raises(ValueError, match="automatic_rollback_enabled"):
        validate_level1_rollback_readiness_verification_manifest(manifest)

    manifest = create_level1_rollback_readiness_verification_manifest(
        project_path=project,
        data_root=data_root,
        rollback_readiness_manifest=_rollback_ready(project, data_root),
        stop_runtime_manifest=_stop_ready(project, data_root),
    )
    manifest["restore_performed"] = True
    with pytest.raises(ValueError, match="restore_performed"):
        validate_level1_rollback_readiness_verification_manifest(manifest)


def test_scale_124_module_has_no_runtime_execution_or_restore_tokens() -> None:
    source = Path("app/atlas/level1_rollback_readiness_verification.py").read_text(encoding="utf-8")
    for token in [
        "subprocess",
        "os.system",
        "shell=True",
        "Popen",
        "check_output",
        "restore_workspace_snapshot",
        "safe_apply(",
        "git push",
        "git pull",
        "git clone",
        "@router.post",
        "/api/atlas/level1/execute",
    ]:
        assert token not in source


def test_scale_124_manifest_and_plan_pointers_advance_to_level1_endpoint() -> None:
    phase = json.loads(Path("docs/atlas_automation_phase_manifest.json").read_text(encoding="utf-8"))
    ui = json.loads(Path("web/atlas_ui_surface_manifest.json").read_text(encoding="utf-8"))
    roadmap = Path("docs/atlas_scale_master_roadmap.md").read_text(encoding="utf-8")
    policy = Path("docs/atlas_autonomous_execution_readiness_policy.md").read_text(encoding="utf-8")

    assert phase["completed_automation_pr"] == "PR-ATLAS-SCALE-124"
    assert phase["current_automation_track"] == "PR-ATLAS-SCALE-125"
    assert phase["next_automation_track"] == "PR-ATLAS-SCALE-125"
    assert phase["current_level"] == "level_0_manual_only"
    assert phase["level1_execution_enabled"] is False
    assert phase["autonomous_execution_enabled"] is False

    assert ui["rollback_readiness_verification_checkpoint"] == "PR-ATLAS-SCALE-124"
    assert ui["rollback_readiness_verification_enabled"] is True
    assert ui["rollback_readiness_verification_verify_only"] is True
    assert ui["rollback_readiness_verification_auto_restore_enabled"] is False
    assert ui["rollback_readiness_verification_auto_rollback_enabled"] is False
    assert ui["rollback_readiness_verification_execution_enabled"] is False
    assert ui["rollback_readiness_verification_next_required_pr"] == "PR-ATLAS-SCALE-125"

    assert "SCALE-124 completed: rollback readiness verification" in roadmap
    assert "PR-ATLAS-SCALE-124 added rollback readiness verification metadata" in policy
