from pathlib import Path

import pytest

from app.atlas.boot_self_diagnosis_checkpoint import (
    CHECK_ATLAS_CONTRACT_SMOKE,
    CHECK_ATLAS_NEXT_MOUNT_DISPLAY_ONLY,
    CHECK_FASTAPI_ROUTER_INCLUDE_SMOKE,
    CHECK_HEALTH_PROBE,
    CHECK_PYTHON_IMPORT_SMOKE,
    CHECK_RECOVERY_SUPERVISOR_AVAILABILITY,
    CHECK_UI_ASSET_EXISTENCE,
    create_boot_self_diagnosis_checkpoint,
    load_boot_self_diagnosis_checkpoint,
    validate_boot_self_diagnosis_checkpoint,
    write_boot_self_diagnosis_checkpoint,
)


def _checks(status: str = "not_run") -> list[dict[str, str]]:
    names = [
        CHECK_PYTHON_IMPORT_SMOKE,
        CHECK_FASTAPI_ROUTER_INCLUDE_SMOKE,
        CHECK_HEALTH_PROBE,
        CHECK_ATLAS_CONTRACT_SMOKE,
        CHECK_UI_ASSET_EXISTENCE,
        CHECK_ATLAS_NEXT_MOUNT_DISPLAY_ONLY,
        CHECK_RECOVERY_SUPERVISOR_AVAILABILITY,
    ]
    return [
        {
            "name": name,
            "status": status,
            "evidence_ref": f"artifact://boot/{name}" if status in {"pass", "fail"} else "",
            "summary": "recorded by caller, not executed by checkpoint helper",
        }
        for name in names
    ]


def test_create_boot_checkpoint_ready_without_execution(tmp_path: Path) -> None:
    store = tmp_path / "checkpoints"
    checkpoint = create_boot_self_diagnosis_checkpoint(
        stable_release_id="stable_001",
        source_commit="abc123",
        release_pointer_path=store / "current_release.json",
        checkpoint_store=store,
        boot_checks=_checks("pass"),
        artifact_hashes={
            "ui.html": "0" * 64,
            "recovery/recover.py": "a" * 64,
        },
        recovery_manifest_path=store / "recovery_manifest.json",
        candidate_workspace_plan_path=store / "candidate_workspace.json",
    )

    assert checkpoint["status"] == "ready"
    assert checkpoint["boot_self_diagnosis_checkpoint_enabled"] is True
    assert checkpoint["stable_checkpoint_artifact_only"] is True
    assert checkpoint["boot_health_artifact_only"] is True
    assert checkpoint["manual_operation_required"] is True
    assert checkpoint["boot_check_execution_enabled"] is False
    assert checkpoint["boot_check_execution_performed"] is False
    assert checkpoint["command_execution_enabled"] is False
    assert checkpoint["health_probe_performed"] is False
    assert checkpoint["import_smoke_performed"] is False
    assert checkpoint["stable_runtime_mutation_enabled"] is False
    assert checkpoint["candidate_workspace_created"] is False
    assert checkpoint["candidate_apply_performed"] is False
    assert checkpoint["promotion_enabled"] is False
    assert checkpoint["direct_merge_enabled"] is False
    assert checkpoint["remote_git_push_enabled"] is False
    assert checkpoint["vue_authoritative"] is False


def test_boot_checkpoint_blocks_missing_required_checks_and_bad_hashes(tmp_path: Path) -> None:
    store = tmp_path / "checkpoints"
    checkpoint = create_boot_self_diagnosis_checkpoint(
        stable_release_id="",
        source_commit="",
        release_pointer_path=tmp_path / "wrong.json",
        checkpoint_store=store,
        boot_checks=[{"name": CHECK_HEALTH_PROBE, "status": "pass", "summary": "missing evidence"}],
        artifact_hashes={"../outside": "bad"},
    )

    assert checkpoint["status"] == "blocked"
    assert checkpoint["boot_self_diagnosis_checkpoint_enabled"] is False
    assert "stable_release_id_required" in checkpoint["blocking_reasons"]
    assert "source_commit_required" in checkpoint["blocking_reasons"]
    assert "release_pointer_filename_required" in checkpoint["blocking_reasons"]
    assert "release_pointer_must_be_under_checkpoint_store" in checkpoint["blocking_reasons"]
    assert "required_boot_checks_missing" in checkpoint["blocking_reasons"]
    assert "boot_check_evidence_required" in checkpoint["blocking_reasons"]
    assert "artifact_hash_path_must_be_repo_relative" in checkpoint["blocking_reasons"]
    assert "artifact_hash_sha256_required" in checkpoint["blocking_reasons"]


def test_validate_rejects_execution_enablement(tmp_path: Path) -> None:
    store = tmp_path / "checkpoints"
    checkpoint = create_boot_self_diagnosis_checkpoint(
        stable_release_id="stable_001",
        source_commit="abc123",
        release_pointer_path=store / "current_release.json",
        checkpoint_store=store,
        boot_checks=_checks("not_run"),
    )
    checkpoint["command_execution_enabled"] = True

    with pytest.raises(ValueError, match="command_execution_enabled"):
        validate_boot_self_diagnosis_checkpoint(checkpoint)


def test_validate_rejects_fabricated_probe_execution(tmp_path: Path) -> None:
    store = tmp_path / "checkpoints"
    checkpoint = create_boot_self_diagnosis_checkpoint(
        stable_release_id="stable_001",
        source_commit="abc123",
        release_pointer_path=store / "current_release.json",
        checkpoint_store=store,
        boot_checks=_checks("not_run"),
    )
    checkpoint["health_probe_performed"] = True

    with pytest.raises(ValueError, match="health_probe_performed"):
        validate_boot_self_diagnosis_checkpoint(checkpoint)


def test_write_and_load_boot_checkpoint(tmp_path: Path) -> None:
    store = tmp_path / "checkpoints"
    checkpoint = create_boot_self_diagnosis_checkpoint(
        stable_release_id="stable_001",
        source_commit="abc123",
        release_pointer_path=store / "current_release.json",
        checkpoint_store=store,
        boot_checks=_checks("not_run"),
    )

    path = write_boot_self_diagnosis_checkpoint(
        checkpoint=checkpoint,
        destination=store / "boot_self_diagnosis.json",
    )
    loaded = load_boot_self_diagnosis_checkpoint(manifest_path=path)

    assert loaded["checkpoint_id"] == checkpoint["checkpoint_id"]
    assert loaded["stable_release_id"] == "stable_001"


def test_boot_checkpoint_source_has_no_runtime_or_process_execution_dependency() -> None:
    text = Path("app/atlas/boot_self_diagnosis_checkpoint.py").read_text(encoding="utf-8")
    forbidden = [
        "subprocess",
        "os.system",
        "requests",
        "from fastapi",
        "import fastapi",
        "uvicorn",
        "import main",
        "from main",
        "safe_apply",
        "git worktree",
    ]
    for needle in forbidden:
        assert needle not in text
