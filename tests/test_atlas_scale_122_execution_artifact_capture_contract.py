from pathlib import Path

import pytest

from app.atlas.level1_execution_artifact_capture import (
    SCHEMA_VERSION,
    create_level1_execution_artifact_manifest,
    load_level1_execution_artifact_manifest,
    validate_level1_execution_artifact_manifest,
    write_level1_execution_artifact_manifest,
)


def test_scale_122_creates_one_action_execution_artifact_without_execution(tmp_path: Path) -> None:
    manifest = create_level1_execution_artifact_manifest(
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

    assert manifest["schema_version"] == SCHEMA_VERSION
    assert manifest["runtime_level"] == "level_0_manual_only"
    assert manifest["manual_only"] is True
    assert manifest["one_action_only"] is True
    assert manifest["loop_enabled"] is False
    assert manifest["auto_continue_enabled"] is False
    assert manifest["execution_enabled"] is False
    assert manifest["level1_execution_enabled"] is False
    assert manifest["autonomous_execution_enabled"] is False
    assert manifest["execution_performed"] is False
    assert manifest["mutation_performed"] is False
    assert manifest["verification_performed"] is False
    assert manifest["rollback_performed"] is False
    assert manifest["retry_performed"] is False
    assert manifest["remote_git_operation_performed"] is False
    assert manifest["backend_authoritative"] is True
    assert manifest["vue_authoritative"] is False
    assert manifest["next_required_pr"] == "PR-ATLAS-SCALE-123"

    path = write_level1_execution_artifact_manifest(data_root=tmp_path, manifest=manifest)
    assert path.exists()
    assert path.is_relative_to(tmp_path)
    loaded = load_level1_execution_artifact_manifest(manifest_path=path, data_root=tmp_path)
    assert loaded["artifact_id"] == manifest["artifact_id"]
    assert loaded["execution_performed"] is False


def test_scale_122_validation_rejects_execution_or_loop_enabled() -> None:
    manifest = create_level1_execution_artifact_manifest(run_id="run_1", action_id="action_1")
    manifest["execution_performed"] = True
    with pytest.raises(ValueError, match="execution_performed"):
        validate_level1_execution_artifact_manifest(manifest)

    manifest = create_level1_execution_artifact_manifest(run_id="run_1", action_id="action_1")
    manifest["loop_enabled"] = True
    with pytest.raises(ValueError, match="loop_enabled"):
        validate_level1_execution_artifact_manifest(manifest)


def test_scale_122_capture_module_has_no_execution_implementation_tokens() -> None:
    source = Path("app/atlas/level1_execution_artifact_capture.py").read_text(encoding="utf-8")
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
        "@router.post",
        "/api/atlas/level1/execute",
    ]:
        assert token not in source
