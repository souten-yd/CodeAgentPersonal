import json
from pathlib import Path

import pytest

from app.atlas.dry_run_artifact_schema import create_dry_run_artifact_manifest
from app.atlas.level1_approval_token_contract import (
    REQUIRED_CONFIRMATION_TEXT,
    create_level1_approval_token_contract,
    validate_level1_approval_token_contract,
)
from app.atlas.level1_disabled_command_runner import build_disabled_single_allowlisted_command_runner_contract
from app.atlas.level1_execution_artifact_capture import create_level1_execution_artifact_manifest
from app.atlas.level1_guarded_single_step_endpoint_contract import create_level1_guarded_single_step_endpoint_contract
from app.atlas.level1_rollback_readiness_verification import create_level1_rollback_readiness_verification_manifest
from app.atlas.level1_runtime_transition_checkpoint import (
    SCHEMA_VERSION,
    create_level1_runtime_transition_checkpoint,
    load_level1_runtime_transition_checkpoint,
    validate_level1_runtime_transition_checkpoint,
    write_level1_runtime_transition_checkpoint,
)
from app.atlas.level1_stop_kill_switch_runtime import create_level1_stop_kill_switch_runtime_manifest
from app.atlas.readiness_gate_rollup import evaluate_readiness_gate_rollup
from app.atlas.rollback_readiness_gate import create_rollback_readiness_record


def _readiness_rollup(project: Path, data_root: Path) -> dict:
    return evaluate_readiness_gate_rollup(
        project_path=project,
        data_root=data_root,
        snapshot_id="snapshot",
        transaction_id="transaction",
        risk_id="risk",
        allowlist_id="allowlist",
        dry_run_gate_id="dry-run",
        rollback_gate_id="rollback",
        artifact_gate_id="artifact",
        stop_gate_id="stop",
        loop_gate_id="loop",
        remote_git_gate_id="remote-git",
        self_improvement_gate_id="self-improvement",
        snapshot_ready=True,
        patch_transaction_ready=True,
        risk_classification_ready=True,
        verification_allowlist_ready=True,
        dry_run_approval_ready=True,
        rollback_readiness_ready=True,
        artifact_capture_ready=True,
        stop_kill_switch_ready=True,
        loop_bound_ready=True,
        remote_git_gate_ready=True,
        self_improvement_gate_ready=True,
        recovery_instructions=["manual rollback available"],
    )


def _endpoint_contract(project: Path, data_root: Path) -> dict:
    dry_run = create_dry_run_artifact_manifest(
        workspace_id="ws_1",
        pool_id="pool_1",
        item_id="item_1",
        run_id="run_1",
        action_id="action_1",
        command_summary="python -m pytest -q tests/test_example.py",
        allowlist_reference="pytest",
        risk_level="low",
        rollback_reference="rollback_gate_1",
        stop_conditions=["stop_requested"],
    )
    token = create_level1_approval_token_contract(
        workspace_id="ws_1",
        pool_id="pool_1",
        item_id="item_1",
        run_id="run_1",
        action_id="action_1",
        dry_run_artifact_id=dry_run["artifact_id"],
        risk_level="low",
        token="approval-secret",
    )
    approval_validation = validate_level1_approval_token_contract(
        contract=token["contract"],
        provided_token="approval-secret",
        confirmation_text=REQUIRED_CONFIRMATION_TEXT,
    )
    runner = build_disabled_single_allowlisted_command_runner_contract(
        command="python -m pytest -q tests/test_example.py",
        project_path=project,
        workspace_id="ws_1",
        pool_id="pool_1",
        item_id="item_1",
        run_id="run_1",
        action_id="action_1",
        risk_level="low",
    )["contract"]
    execution_artifact = create_level1_execution_artifact_manifest(
        workspace_id="ws_1",
        pool_id="pool_1",
        item_id="item_1",
        run_id="run_1",
        action_id="action_1",
        runner_id=runner["runner_id"],
        dry_run_artifact_id=dry_run["artifact_id"],
        allowlist_id=runner["allowlist_id"],
        risk_level="low",
    )
    stop_runtime = create_level1_stop_kill_switch_runtime_manifest(
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
    rollback_record = create_rollback_readiness_record(
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
    rollback_verification = create_level1_rollback_readiness_verification_manifest(
        project_path=project,
        data_root=data_root,
        workspace_id="ws_1",
        pool_id="pool_1",
        item_id="item_1",
        run_id="run_1",
        action_id="action_1",
        rollback_readiness_manifest=rollback_record["manifest"],
        stop_runtime_manifest=stop_runtime,
    )
    return create_level1_guarded_single_step_endpoint_contract(
        project_path=project,
        data_root=data_root,
        workspace_id="ws_1",
        pool_id="pool_1",
        item_id="item_1",
        run_id="run_1",
        action_id="action_1",
        requested_command="python -m pytest -q tests/test_example.py",
        risk_level="low",
        dry_run_artifact_manifest=dry_run,
        approval_token_validation=approval_validation,
        disabled_runner_contract=runner,
        execution_artifact_manifest=execution_artifact,
        stop_runtime_manifest=stop_runtime,
        rollback_verification_manifest=rollback_verification,
    )


def test_scale_127_authorizes_level1_checkpoint_without_performing_execution(tmp_path: Path) -> None:
    project = tmp_path / "project"
    data_root = tmp_path / "data"
    project.mkdir()
    checkpoint = create_level1_runtime_transition_checkpoint(
        project_path=project,
        data_root=data_root,
        readiness_rollup=_readiness_rollup(project, data_root),
        endpoint_contract=_endpoint_contract(project, data_root),
        workspace_id="ws_1",
        pool_id="pool_1",
        item_id="item_1",
        run_id="run_1",
        action_id="action_1",
    )

    assert checkpoint["schema_version"] == SCHEMA_VERSION
    assert checkpoint["transition_pr"] == "PR-ATLAS-SCALE-127"
    assert checkpoint["previous_runtime_level"] == "level_0_manual_only"
    assert checkpoint["runtime_level"] == "level_1_guarded_single_step"
    assert checkpoint["transition_authorized"] is True
    assert checkpoint["level1_execution_enabled"] is True
    assert checkpoint["level1_single_step_execution_allowed"] is True
    assert checkpoint["callable_execution_endpoint_policy_enabled"] is True
    assert checkpoint["public_execution_route_added"] is False
    assert checkpoint["dry_run_required"] is True
    assert checkpoint["explicit_approval_required"] is True
    assert checkpoint["single_action_only"] is True
    assert checkpoint["autonomous_execution_enabled"] is False
    assert checkpoint["auto_continue_enabled"] is False
    assert checkpoint["patch_apply_enabled"] is False
    assert checkpoint["remote_git_operations_enabled"] is False
    assert checkpoint["vue_authoritative"] is False
    assert checkpoint["execution_performed"] is False
    assert checkpoint["mutation_performed"] is False
    assert checkpoint["blocking_reasons"] == []

    path = write_level1_runtime_transition_checkpoint(data_root=data_root, checkpoint=checkpoint)
    assert path.exists()
    assert path.is_relative_to(data_root)
    loaded = load_level1_runtime_transition_checkpoint(manifest_path=path, data_root=data_root)
    assert loaded["checkpoint_id"] == checkpoint["checkpoint_id"]


def test_scale_127_blocks_when_required_gate_evidence_is_missing(tmp_path: Path) -> None:
    project = tmp_path / "project"
    data_root = tmp_path / "data"
    project.mkdir()
    rollup = _readiness_rollup(project, data_root)
    rollup["readiness_rollup_ready"] = False
    checkpoint = create_level1_runtime_transition_checkpoint(
        project_path=project,
        data_root=data_root,
        readiness_rollup=rollup,
        endpoint_contract=_endpoint_contract(project, data_root),
    )

    assert checkpoint["transition_authorized"] is False
    assert checkpoint["transition_blocked"] is True
    assert checkpoint["level1_execution_enabled"] is False
    assert "readiness_rollup_ready_required" in checkpoint["blocking_reasons"]


def test_scale_127_validation_rejects_forbidden_capabilities(tmp_path: Path) -> None:
    project = tmp_path / "project"
    data_root = tmp_path / "data"
    project.mkdir()
    checkpoint = create_level1_runtime_transition_checkpoint(
        project_path=project,
        data_root=data_root,
        readiness_rollup=_readiness_rollup(project, data_root),
        endpoint_contract=_endpoint_contract(project, data_root),
    )
    checkpoint["autonomous_execution_enabled"] = True
    with pytest.raises(ValueError, match="autonomous_execution_enabled"):
        validate_level1_runtime_transition_checkpoint(checkpoint)

    checkpoint = create_level1_runtime_transition_checkpoint(
        project_path=project,
        data_root=data_root,
        readiness_rollup=_readiness_rollup(project, data_root),
        endpoint_contract=_endpoint_contract(project, data_root),
    )
    checkpoint["public_execution_route_added"] = True
    with pytest.raises(ValueError, match="public_execution_route_added"):
        validate_level1_runtime_transition_checkpoint(checkpoint)


def test_scale_127_module_has_no_execution_or_mutation_tokens() -> None:
    source = Path("app/atlas/level1_runtime_transition_checkpoint.py").read_text(encoding="utf-8")
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


def test_scale_127_manifest_and_plan_pointers_advance_to_patch_proposal() -> None:
    phase = json.loads(Path("docs/atlas_automation_phase_manifest.json").read_text(encoding="utf-8"))
    ui = json.loads(Path("web/atlas_ui_surface_manifest.json").read_text(encoding="utf-8"))
    roadmap = Path("docs/atlas_scale_master_roadmap.md").read_text(encoding="utf-8")
    policy = Path("docs/atlas_autonomous_execution_readiness_policy.md").read_text(encoding="utf-8")

    completed_scale = int(phase["completed_automation_pr"].rsplit("-", 1)[1])
    assert completed_scale >= 127
    assert phase["current_automation_track"].startswith("PR-ATLAS-SCALE-")
    assert phase["next_automation_track"].startswith("PR-ATLAS-SCALE-")
    assert phase["current_level"] == "level_1_guarded_single_step"
    assert phase["level1_execution_enabled"] is True
    assert phase["autonomous_execution_enabled"] is False

    assert ui["level1_runtime_transition_checkpoint"] == "PR-ATLAS-SCALE-127"
    assert ui["level1_runtime_transition_previous_level"] == "level_0_manual_only"
    assert ui["level1_runtime_transition_runtime_level"] == "level_1_guarded_single_step"
    assert ui["level1_runtime_transition_level1_execution_enabled"] is True
    assert ui["level1_runtime_transition_public_route_added"] is False
    assert ui["level1_runtime_transition_autonomous_execution_enabled"] is False
    assert ui["level1_runtime_transition_next_required_pr"] == "PR-ATLAS-SCALE-128"

    assert "SCALE-127 completed: explicit Level-1 runtime transition checkpoint" in roadmap
    assert "PR-ATLAS-SCALE-127 is the explicit Level-1 runtime transition checkpoint" in policy
