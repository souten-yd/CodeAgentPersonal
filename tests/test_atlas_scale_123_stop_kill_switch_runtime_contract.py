import json
from pathlib import Path

import pytest

from app.atlas.level1_execution_artifact_capture import create_level1_execution_artifact_manifest
from app.atlas.level1_stop_kill_switch_runtime import (
    SCHEMA_VERSION,
    create_level1_stop_kill_switch_runtime_manifest,
    load_level1_stop_kill_switch_runtime_manifest,
    validate_level1_stop_kill_switch_runtime_manifest,
    write_level1_stop_kill_switch_runtime_manifest,
)


def _execution_artifact() -> dict:
    return create_level1_execution_artifact_manifest(
        workspace_id="ws_1",
        pool_id="pool_1",
        item_id="item_1",
        run_id="run_1",
        action_id="action_1",
        command_summary="candidate command metadata",
        runner_id="disabled_runner_1",
        dry_run_artifact_id="dry_run_artifact_1",
        allowlist_id="allow_1",
        risk_level="low",
    )


def test_scale_123_integrates_stop_gate_without_execution(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    manifest = create_level1_stop_kill_switch_runtime_manifest(
        project_path=project,
        data_root=tmp_path / "data",
        workspace_id="ws_1",
        pool_id="pool_1",
        item_id="item_1",
        run_id="run_1",
        action_id="action_1",
        execution_artifact_manifest=_execution_artifact(),
        execution_artifact_manifest_path=str(tmp_path / "execution-artifact.json"),
    )

    assert manifest["schema_version"] == SCHEMA_VERSION
    assert manifest["runtime_level"] == "level_0_manual_only"
    assert manifest["runtime_integration_ready"] is True
    assert manifest["stop_gate_ready"] is True
    assert manifest["execution_artifact_valid"] is True
    assert manifest["manual_only"] is True
    assert manifest["continuation_after_stop_allowed"] is False
    assert manifest["auto_continue_enabled"] is False
    assert manifest["execute_all_enabled"] is False
    assert manifest["execution_enabled"] is False
    assert manifest["level1_execution_enabled"] is False
    assert manifest["autonomous_execution_enabled"] is False
    assert manifest["execution_performed"] is False
    assert manifest["mutation_performed"] is False
    assert manifest["verification_performed"] is False
    assert manifest["rollback_performed"] is False
    assert manifest["retry_performed"] is False
    assert manifest["process_kill_performed"] is False
    assert manifest["backend_authoritative"] is True
    assert manifest["vue_authoritative"] is False
    assert manifest["next_required_pr"] == "PR-ATLAS-SCALE-124"

    path = write_level1_stop_kill_switch_runtime_manifest(data_root=tmp_path / "data", manifest=manifest)
    assert path.exists()
    assert path.is_relative_to(tmp_path / "data")
    loaded = load_level1_stop_kill_switch_runtime_manifest(manifest_path=path, data_root=tmp_path / "data")
    assert loaded["runtime_integration_id"] == manifest["runtime_integration_id"]


def test_scale_123_stop_requested_blocks_continuation(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    manifest = create_level1_stop_kill_switch_runtime_manifest(
        project_path=project,
        data_root=tmp_path / "data",
        execution_artifact_manifest=_execution_artifact(),
        stop_requested=True,
        stop_request_id="stop_1",
    )

    assert manifest["stop_requested"] is True
    assert manifest["continuation_blocked"] is True
    assert "stop_state_blocks_continuation" in manifest["blocking_reasons"]


def test_scale_123_validation_rejects_execution_or_continue_after_stop() -> None:
    manifest = create_level1_stop_kill_switch_runtime_manifest(
        project_path=Path.cwd(),
        execution_artifact_manifest=_execution_artifact(),
    )
    manifest["execution_performed"] = True
    with pytest.raises(ValueError, match="execution_performed"):
        validate_level1_stop_kill_switch_runtime_manifest(manifest)

    manifest = create_level1_stop_kill_switch_runtime_manifest(
        project_path=Path.cwd(),
        execution_artifact_manifest=_execution_artifact(),
        stop_requested=True,
    )
    manifest["continuation_blocked"] = False
    with pytest.raises(ValueError, match="stop_requested_must_block_continuation"):
        validate_level1_stop_kill_switch_runtime_manifest(manifest)


def test_scale_123_module_has_no_execution_or_process_kill_tokens() -> None:
    source = Path("app/atlas/level1_stop_kill_switch_runtime.py").read_text(encoding="utf-8")
    for token in [
        "subprocess",
        "os.system",
        "shell=True",
        "Popen",
        "check_output",
        "safe_apply",
        "git push",
        "git pull",
        "git clone",
        "os.kill",
        "terminate(",
        "kill(",
        "@router.post",
        "/api/atlas/level1/execute",
    ]:
        assert token not in source


def test_scale_123_manifest_and_plan_pointers_advance_to_rollback_readiness() -> None:
    phase = json.loads(Path("docs/atlas_automation_phase_manifest.json").read_text(encoding="utf-8"))
    ui = json.loads(Path("web/atlas_ui_surface_manifest.json").read_text(encoding="utf-8"))
    roadmap = Path("docs/atlas_scale_master_roadmap.md").read_text(encoding="utf-8")
    policy = Path("docs/atlas_autonomous_execution_readiness_policy.md").read_text(encoding="utf-8")

    completed_scale = int(phase["completed_automation_pr"].rsplit("-", 1)[1])
    assert completed_scale >= 123
    assert phase["current_automation_track"].startswith("PR-ATLAS-SCALE-")
    assert phase["next_automation_track"].startswith("PR-ATLAS-SCALE-")
    assert phase["autonomous_execution_enabled"] is False

    assert ui["stop_kill_switch_runtime_integration_checkpoint"] == "PR-ATLAS-SCALE-123"
    assert ui["stop_kill_switch_runtime_integration_enabled"] is True
    assert ui["stop_kill_switch_runtime_integration_display_only"] is True
    assert ui["stop_kill_switch_runtime_integration_blocks_continuation"] is True
    assert ui["stop_kill_switch_runtime_integration_kills_processes"] is False
    assert ui["stop_kill_switch_runtime_integration_stops_real_jobs"] is False
    assert ui["stop_kill_switch_runtime_integration_execution_enabled"] is False
    assert ui["stop_kill_switch_runtime_integration_mutation_enabled"] is False
    assert ui["stop_kill_switch_runtime_integration_next_required_pr"] == "PR-ATLAS-SCALE-124"
    assert ui["autonomous_execution_runtime_level"] == "level_0_manual_only"

    assert "SCALE-123 completed: stop / kill-switch runtime integration" in roadmap
    assert "stop / kill-switch runtime integration metadata" in policy or "SCALE-123 completed" in roadmap
