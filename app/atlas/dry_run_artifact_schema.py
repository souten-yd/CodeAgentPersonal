from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "atlas.dry_run_artifact.v1"
SUPPORTED_SCHEMA_VERSIONS = frozenset({SCHEMA_VERSION})
_RUNTIME_LEVEL = "level_0_manual_only"

REQUIRED_FIELDS: tuple[str, ...] = (
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


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_under(root: Path, target: Path, code: str) -> Path:
    rr = root.resolve()
    tt = target.resolve()
    if os.path.commonpath([str(rr), str(tt)]) != str(rr):
        raise ValueError(code)
    return tt


def _build_artifact_id(*, run_id: str, action_id: str, created_at: str) -> str:
    created_norm = created_at.replace(":", "").replace("-", "").replace("+", "").replace(".", "")
    return f"dra_{run_id or 'run'}_{action_id or 'action'}_{created_norm}"


def create_dry_run_artifact_manifest(
    *,
    workspace_id: str,
    pool_id: str,
    item_id: str,
    run_id: str,
    action_id: str,
    command_summary: str,
    allowlist_reference: str,
    risk_level: str,
    expected_artifacts: list[str] | None = None,
    verification_targets: list[str] | None = None,
    rollback_reference: str = "",
    stop_conditions: list[str] | None = None,
    policy_notes: list[str] | None = None,
    warnings: list[str] | None = None,
    created_at: str | None = None,
    schema_version: str = SCHEMA_VERSION,
) -> dict[str, Any]:
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ValueError("unsupported_schema_version")

    created = created_at or _utc_now()
    manifest = {
        "artifact_id": _build_artifact_id(run_id=run_id, action_id=action_id, created_at=created),
        "schema_version": schema_version,
        "created_at": created,
        "workspace_id": workspace_id,
        "pool_id": pool_id,
        "item_id": item_id,
        "run_id": run_id,
        "action_id": action_id,
        "runtime_level": _RUNTIME_LEVEL,
        "manual_only": True,
        "dry_run_only": True,
        "advisory_only": True,
        "execution_enabled": False,
        "level1_execution_enabled": False,
        "autonomous_execution_enabled": False,
        "backend_authoritative": True,
        "vue_authoritative": False,
        "command_summary": command_summary,
        "allowlist_reference": allowlist_reference,
        "risk_level": risk_level,
        "expected_artifacts": list(expected_artifacts or []),
        "verification_targets": list(verification_targets or []),
        "rollback_reference": rollback_reference,
        "stop_conditions": list(stop_conditions or []),
        "policy_notes": list(policy_notes or []),
        "warnings": list(warnings or []),
    }
    validate_dry_run_artifact_manifest(manifest)
    return manifest


def validate_dry_run_artifact_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    missing = [field for field in REQUIRED_FIELDS if field not in manifest]
    if missing:
        raise ValueError(f"missing_required_fields:{','.join(missing)}")
    if manifest.get("schema_version") not in SUPPORTED_SCHEMA_VERSIONS:
        raise ValueError("unsupported_schema_version")

    invariant_checks = {
        "runtime_level": manifest.get("runtime_level") == _RUNTIME_LEVEL,
        "manual_only": manifest.get("manual_only") is True,
        "dry_run_only": manifest.get("dry_run_only") is True,
        "advisory_only": manifest.get("advisory_only") is True,
        "execution_enabled": manifest.get("execution_enabled") is False,
        "level1_execution_enabled": manifest.get("level1_execution_enabled") is False,
        "autonomous_execution_enabled": manifest.get("autonomous_execution_enabled") is False,
        "backend_authoritative": manifest.get("backend_authoritative") is True,
        "vue_authoritative": manifest.get("vue_authoritative") is False,
    }
    violations = sorted([name for name, ok in invariant_checks.items() if not ok])
    if violations:
        raise ValueError(f"invariant_violation:{','.join(violations)}")
    return manifest


def write_dry_run_artifact_manifest(*, data_root: str | Path, manifest: dict[str, Any]) -> Path:
    validated = validate_dry_run_artifact_manifest(manifest)
    root = Path(data_root).expanduser().resolve()
    artifact_id = str(validated.get("artifact_id") or "")
    if not artifact_id:
        raise ValueError("artifact_id_required")

    manifest_path = root / "atlas" / "dry_run_artifacts" / artifact_id / "manifest.json"
    _ensure_under(root, manifest_path, "manifest_outside_data_root")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(validated, indent=2, sort_keys=True), encoding="utf-8")
    return manifest_path


def load_dry_run_artifact_manifest(
    *,
    data_root: str | Path | None = None,
    manifest_path: str | Path,
) -> dict[str, Any]:
    path = Path(manifest_path).expanduser().resolve()
    if data_root is not None:
        root = Path(data_root).expanduser().resolve()
        _ensure_under(root, path, "manifest_outside_data_root")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return validate_dry_run_artifact_manifest(payload)
