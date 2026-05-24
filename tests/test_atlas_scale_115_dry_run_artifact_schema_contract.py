from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from app.atlas.dry_run_artifact_schema import (
    REQUIRED_FIELDS,
    SCHEMA_VERSION,
    create_dry_run_artifact_manifest,
    load_dry_run_artifact_manifest,
    validate_dry_run_artifact_manifest,
    write_dry_run_artifact_manifest,
)

FORBIDDEN_STRINGS = (
    "subprocess",
    "patch apply",
    "git ",
    "self-modification",
)


def _make_manifest() -> dict[str, object]:
    return create_dry_run_artifact_manifest(
        workspace_id="ws_1",
        pool_id="pool_1",
        item_id="item_1",
        run_id="run_1",
        action_id="action_1",
        command_summary="review-only planned action summary",
        allowlist_reference="allowlist:v1",
        risk_level="medium",
        expected_artifacts=["risk_manifest.json"],
        verification_targets=["tests/test_atlas_scale_115_dry_run_artifact_schema_contract.py"],
        rollback_reference="rollback:manual",
        stop_conditions=["manual_abort"],
        policy_notes=["metadata_only"],
        warnings=["advisory_only"],
        created_at="2026-01-01T00:00:00+00:00",
    )


def test_scale_115_schema_stability_required_fields() -> None:
    assert REQUIRED_FIELDS == (
        "artifact_id",
        "schema_version",
        "created_at",
        "workspace_id",
        "pool_id",
        "item_id",
        "run_id",
        "action_id",
        "runtime_level",
        "manual_only",
        "dry_run_only",
        "advisory_only",
        "execution_enabled",
        "level1_execution_enabled",
        "autonomous_execution_enabled",
        "backend_authoritative",
        "vue_authoritative",
        "command_summary",
        "allowlist_reference",
        "risk_level",
        "expected_artifacts",
        "verification_targets",
        "rollback_reference",
        "stop_conditions",
        "policy_notes",
        "warnings",
    )


def test_scale_115_deterministic_manifest_and_invariants() -> None:
    manifest = _make_manifest()
    assert manifest["schema_version"] == SCHEMA_VERSION
    assert manifest["runtime_level"] == "level_0_manual_only"
    assert manifest["manual_only"] is True
    assert manifest["advisory_only"] is True
    assert manifest["dry_run_only"] is True
    assert manifest["execution_enabled"] is False
    assert manifest["level1_execution_enabled"] is False
    assert manifest["autonomous_execution_enabled"] is False
    assert manifest["backend_authoritative"] is True
    assert manifest["vue_authoritative"] is False


def test_scale_115_manifest_persistence_roundtrip(tmp_path: Path) -> None:
    manifest = _make_manifest()
    out = write_dry_run_artifact_manifest(data_root=tmp_path, manifest=manifest)
    loaded = load_dry_run_artifact_manifest(data_root=tmp_path, manifest_path=out)
    assert loaded == manifest
    assert out == tmp_path / "atlas" / "dry_run_artifacts" / manifest["artifact_id"] / "manifest.json"


def test_scale_115_rejects_unsupported_schema_version() -> None:
    manifest = _make_manifest()
    manifest["schema_version"] = "atlas.dry_run_artifact.v2"
    with pytest.raises(ValueError, match="unsupported_schema_version"):
        validate_dry_run_artifact_manifest(manifest)


def test_scale_115_forbids_execution_mutation_git_self_modification_strings() -> None:
    target = Path("app/atlas/dry_run_artifact_schema.py").read_text(encoding="utf-8").lower()
    for token in FORBIDDEN_STRINGS:
        assert token not in target


def test_scale_115_rejects_manifest_path_outside_data_root(tmp_path: Path) -> None:
    manifest = _make_manifest()
    out = write_dry_run_artifact_manifest(data_root=tmp_path, manifest=manifest)
    with pytest.raises(ValueError, match="manifest_outside_data_root"):
        load_dry_run_artifact_manifest(data_root=tmp_path / "other_root", manifest_path=out)


def test_scale_115_plan_validator_subprocess_contract() -> None:
    result = subprocess.run(
        ["python", "scripts/validate_atlas_automation_plan.py"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Atlas automation plan contract OK" in result.stdout
