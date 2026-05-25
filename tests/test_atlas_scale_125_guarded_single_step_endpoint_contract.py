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
from app.atlas.level1_guarded_single_step_endpoint_contract import (
    SCHEMA_VERSION,
    create_level1_guarded_single_step_endpoint_contract,
    load_level1_guarded_single_step_endpoint_contract,
    validate_level1_guarded_single_step_endpoint_contract,
    write_level1_guarded_single_step_endpoint_contract,
)
from app.atlas.level1_rollback_readiness_verification import (
    create_level1_rollback_readiness_verification_manifest,
)
from app.atlas.level1_stop_kill_switch_runtime import create_level1_stop_kill_switch_runtime_manifest
from app.atlas.rollback_readiness_gate import create_rollback_readiness_record


def _evidence(project: Path, data_root: Path) -> dict:
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
    return {
        "dry_run_artifact_manifest": dry_run,
        "approval_token_validation": approval_validation,
        "disabled_runner_contract": runner,
        "execution_artifact_manifest": execution_artifact,
        "stop_runtime_manifest": stop_runtime,
        "rollback_verification_manifest": rollback_verification,
    }


def test_scale_125_builds_guarded_endpoint_contract_without_enabling_runtime_execution(tmp_path: Path) -> None:
    project = tmp_path / "project"
    data_root = tmp_path / "data"
    project.mkdir()
    contract = create_level1_guarded_single_step_endpoint_contract(
        project_path=project,
        data_root=data_root,
        workspace_id="ws_1",
        pool_id="pool_1",
        item_id="item_1",
        run_id="run_1",
        action_id="action_1",
        requested_command="python -m pytest -q tests/test_example.py",
        risk_level="low",
        **_evidence(project, data_root),
    )

    assert contract["schema_version"] == SCHEMA_VERSION
    assert contract["runtime_level"] == "level_0_manual_only"
    assert contract["target_runtime_level"] == "level_1_guarded_single_step"
    assert contract["next_runtime_transition_pr"] == "PR-ATLAS-SCALE-127"
    assert contract["endpoint_contract_ready"] is True
    assert contract["limited_execution_candidate"] is True
    assert contract["single_action_only"] is True
    assert contract["dry_run_required"] is True
    assert contract["explicit_approval_required"] is True
    assert contract["callable_execution_endpoint_enabled"] is False
    assert contract["current_runtime_allows_execution"] is False
    assert contract["execution_blocked_until_runtime_transition"] is True
    assert contract["execution_enabled"] is False
    assert contract["level1_execution_enabled"] is False
    assert contract["autonomous_execution_enabled"] is False
    assert contract["execution_performed"] is False
    assert contract["mutation_performed"] is False
    assert contract["verification_performed"] is False
    assert contract["rollback_performed"] is False
    assert contract["restore_performed"] is False
    assert contract["auto_continue_enabled"] is False
    assert contract["execute_all_enabled"] is False
    assert contract["backend_authoritative"] is True
    assert contract["vue_authoritative"] is False
    assert contract["next_required_pr"] == "PR-ATLAS-SCALE-126"
    assert "runtime_transition_required_before_execution" in contract["blocking_reasons"]

    path = write_level1_guarded_single_step_endpoint_contract(data_root=data_root, contract=contract)
    assert path.exists()
    assert path.is_relative_to(data_root)
    loaded = load_level1_guarded_single_step_endpoint_contract(manifest_path=path, data_root=data_root)
    assert loaded["endpoint_contract_id"] == contract["endpoint_contract_id"]


def test_scale_125_blocks_missing_approval_or_non_low_risk(tmp_path: Path) -> None:
    project = tmp_path / "project"
    data_root = tmp_path / "data"
    project.mkdir()
    evidence = _evidence(project, data_root)
    evidence["approval_token_validation"] = {}
    contract = create_level1_guarded_single_step_endpoint_contract(
        project_path=project,
        data_root=data_root,
        risk_level="medium",
        **evidence,
    )

    assert contract["endpoint_contract_ready"] is False
    assert "approval_token" in contract["missing_requirements"]
    assert "low_risk_level" in contract["missing_requirements"]
    assert contract["execution_enabled"] is False
    assert contract["callable_execution_endpoint_enabled"] is False


def test_scale_125_validation_rejects_execution_enablement(tmp_path: Path) -> None:
    project = tmp_path / "project"
    data_root = tmp_path / "data"
    project.mkdir()
    contract = create_level1_guarded_single_step_endpoint_contract(
        project_path=project,
        data_root=data_root,
        risk_level="low",
        **_evidence(project, data_root),
    )
    contract["execution_enabled"] = True
    with pytest.raises(ValueError, match="execution_enabled"):
        validate_level1_guarded_single_step_endpoint_contract(contract)

    contract = create_level1_guarded_single_step_endpoint_contract(
        project_path=project,
        data_root=data_root,
        risk_level="low",
        **_evidence(project, data_root),
    )
    contract["callable_execution_endpoint_enabled"] = True
    with pytest.raises(ValueError, match="callable_execution_endpoint_enabled"):
        validate_level1_guarded_single_step_endpoint_contract(contract)


def test_scale_125_module_has_no_public_route_or_execution_tokens() -> None:
    source = Path("app/atlas/level1_guarded_single_step_endpoint_contract.py").read_text(encoding="utf-8")
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


def test_scale_125_manifest_and_plan_pointers_advance_to_ui_review_panel() -> None:
    phase = json.loads(Path("docs/atlas_automation_phase_manifest.json").read_text(encoding="utf-8"))
    ui = json.loads(Path("web/atlas_ui_surface_manifest.json").read_text(encoding="utf-8"))
    roadmap = Path("docs/atlas_scale_master_roadmap.md").read_text(encoding="utf-8")

    completed_scale = int(phase["completed_automation_pr"].rsplit("-", 1)[1])
    assert completed_scale >= 125
    assert phase["current_automation_track"].startswith("PR-ATLAS-SCALE-")
    assert phase["next_automation_track"].startswith("PR-ATLAS-SCALE-")
    assert phase["current_level"] == "level_0_manual_only"
    assert phase["level1_execution_enabled"] is False
    assert phase["autonomous_execution_enabled"] is False

    assert ui["level1_guarded_single_step_endpoint_checkpoint"] == "PR-ATLAS-SCALE-125"
    assert ui["level1_guarded_single_step_endpoint_contract_enabled"] is True
    assert ui["level1_guarded_single_step_endpoint_callable_route_enabled"] is False
    assert ui["level1_guarded_single_step_endpoint_execution_enabled"] is False
    assert ui["level1_guarded_single_step_endpoint_requires_dry_run"] is True
    assert ui["level1_guarded_single_step_endpoint_requires_approval"] is True
    assert ui["level1_guarded_single_step_endpoint_next_required_pr"] == "PR-ATLAS-SCALE-126"

    assert "SCALE-125 completed: Level-1 guarded single-step endpoint contract" in roadmap
