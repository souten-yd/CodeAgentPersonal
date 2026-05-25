from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.atlas.level1_stop_kill_switch_runtime import (
    validate_level1_stop_kill_switch_runtime_manifest,
)

SCHEMA_VERSION = "atlas.level1_rollback_readiness_verification.v1"
RUNTIME_LEVEL = "level_0_manual_only"


def create_level1_rollback_readiness_verification_manifest(
    *,
    project_path: str | Path,
    data_root: str | Path | None = None,
    workspace_id: str = "default",
    pool_id: str = "",
    item_id: str = "",
    run_id: str = "",
    action_id: str = "",
    rollback_readiness_manifest: dict[str, Any] | None = None,
    rollback_readiness_manifest_path: str = "",
    stop_runtime_manifest: dict[str, Any] | None = None,
    stop_runtime_manifest_path: str = "",
    verification_reason: str = "",
    warnings: list[str] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    created = created_at or _utc_now()
    project_root = Path(project_path).expanduser().resolve()
    root = Path(data_root).expanduser().resolve() if data_root is not None else project_root
    rollback_manifest = dict(rollback_readiness_manifest or {})
    stop_manifest = dict(stop_runtime_manifest or {})

    rollback_checks = _evaluate_rollback_readiness_manifest(rollback_manifest)
    stop_checks = _evaluate_stop_runtime_manifest(stop_manifest)
    blocking_reasons = [
        *rollback_checks["blocking_reasons"],
        *stop_checks["blocking_reasons"],
    ]
    rollback_verified = not blocking_reasons

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "verification_id": _verification_id(run_id=run_id, action_id=action_id, created_at=created),
        "created_at": created,
        "workspace_id": _safe_text(workspace_id, "default"),
        "pool_id": _safe_text(pool_id),
        "item_id": _safe_text(item_id),
        "run_id": _safe_text(run_id, "run"),
        "action_id": _safe_text(action_id, "action"),
        "verification_reason": _safe_text(verification_reason),
        "project_path": str(project_root),
        "data_root": str(root),
        "runtime_level": RUNTIME_LEVEL,
        "manual_only": True,
        "verify_only": True,
        "rollback_readiness_verified": rollback_verified,
        "rollback_ready": rollback_checks["rollback_ready"],
        "rollback_readiness_manifest_path": _safe_text(rollback_readiness_manifest_path),
        "rollback_gate_id": rollback_checks["rollback_gate_id"],
        "restore_plan_valid": rollback_checks["restore_plan_valid"],
        "snapshot_manifest_valid": rollback_checks["snapshot_manifest_valid"],
        "snapshot_path_safety_valid": rollback_checks["snapshot_path_safety_valid"],
        "transaction_rollback_metadata_valid": rollback_checks["transaction_rollback_metadata_valid"],
        "dry_run_gate_ready": rollback_checks["dry_run_gate_ready"],
        "restore_supported": rollback_checks["restore_supported"],
        "restore_manual_only": True,
        "rollback_strategy": rollback_checks["rollback_strategy"],
        "risk_level": rollback_checks["risk_level"],
        "risk_requires_human_review": rollback_checks["risk_requires_human_review"],
        "stop_runtime_integration_verified": stop_checks["stop_runtime_integration_verified"],
        "stop_runtime_manifest_path": _safe_text(stop_runtime_manifest_path),
        "stop_runtime_integration_id": stop_checks["stop_runtime_integration_id"],
        "stop_blocks_continuation": stop_checks["stop_blocks_continuation"],
        "automatic_rollback_enabled": False,
        "automatic_restore_enabled": False,
        "automatic_execute_enabled": False,
        "automatic_safe_apply_enabled": False,
        "automatic_verification_enabled": False,
        "automatic_retry_enabled": False,
        "automatic_patch_apply_enabled": False,
        "autonomous_execution_enabled": False,
        "level1_execution_enabled": False,
        "execution_enabled": False,
        "rollback_performed": False,
        "restore_performed": False,
        "mutation_performed": False,
        "verification_performed": False,
        "backend_authoritative": True,
        "vue_authoritative": False,
        "missing_requirements": sorted(set([*rollback_checks["missing_requirements"], *stop_checks["missing_requirements"]])),
        "blocking_reasons": sorted(set(blocking_reasons)),
        "warnings": sorted(set([*_safe_list(warnings), *rollback_checks["warnings"], *stop_checks["warnings"]])),
        "policy_notes": [
            "scale_124_rollback_readiness_verification",
            "verify_only",
            "no_automatic_rollback",
            "no_restore_performed",
            "no_runtime_level_change",
        ],
        "summary": {
            "rollback_readiness_verified": rollback_verified,
            "rollback_gate_id": rollback_checks["rollback_gate_id"],
            "stop_runtime_integration_id": stop_checks["stop_runtime_integration_id"],
            "manual_only": True,
        },
        "next_required_pr": "PR-ATLAS-SCALE-125",
    }
    return validate_level1_rollback_readiness_verification_manifest(manifest)


def validate_level1_rollback_readiness_verification_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    required = [
        "schema_version",
        "verification_id",
        "runtime_level",
        "manual_only",
        "verify_only",
        "rollback_readiness_verified",
        "restore_manual_only",
        "stop_runtime_integration_verified",
        "stop_blocks_continuation",
        "automatic_rollback_enabled",
        "automatic_restore_enabled",
        "automatic_execute_enabled",
        "automatic_safe_apply_enabled",
        "automatic_verification_enabled",
        "automatic_retry_enabled",
        "autonomous_execution_enabled",
        "level1_execution_enabled",
        "execution_enabled",
        "rollback_performed",
        "restore_performed",
        "mutation_performed",
        "verification_performed",
        "backend_authoritative",
        "vue_authoritative",
    ]
    missing = [field for field in required if field not in manifest]
    if missing:
        raise ValueError(f"missing_required_fields:{','.join(missing)}")
    invariants = {
        "schema_version": manifest.get("schema_version") == SCHEMA_VERSION,
        "runtime_level": manifest.get("runtime_level") == RUNTIME_LEVEL,
        "manual_only": manifest.get("manual_only") is True,
        "verify_only": manifest.get("verify_only") is True,
        "restore_manual_only": manifest.get("restore_manual_only") is True,
        "automatic_rollback_enabled": manifest.get("automatic_rollback_enabled") is False,
        "automatic_restore_enabled": manifest.get("automatic_restore_enabled") is False,
        "automatic_execute_enabled": manifest.get("automatic_execute_enabled") is False,
        "automatic_safe_apply_enabled": manifest.get("automatic_safe_apply_enabled") is False,
        "automatic_verification_enabled": manifest.get("automatic_verification_enabled") is False,
        "automatic_retry_enabled": manifest.get("automatic_retry_enabled") is False,
        "automatic_patch_apply_enabled": manifest.get("automatic_patch_apply_enabled") is False,
        "autonomous_execution_enabled": manifest.get("autonomous_execution_enabled") is False,
        "level1_execution_enabled": manifest.get("level1_execution_enabled") is False,
        "execution_enabled": manifest.get("execution_enabled") is False,
        "rollback_performed": manifest.get("rollback_performed") is False,
        "restore_performed": manifest.get("restore_performed") is False,
        "mutation_performed": manifest.get("mutation_performed") is False,
        "verification_performed": manifest.get("verification_performed") is False,
        "backend_authoritative": manifest.get("backend_authoritative") is True,
        "vue_authoritative": manifest.get("vue_authoritative") is False,
    }
    violations = [key for key, ok in invariants.items() if not ok]
    if violations:
        raise ValueError(f"invariant_violation:{','.join(sorted(violations))}")
    if manifest.get("rollback_readiness_verified") and manifest.get("blocking_reasons"):
        raise ValueError("invariant_violation:verified_with_blocking_reasons")
    if manifest.get("rollback_readiness_verified") and manifest.get("stop_blocks_continuation") is not True:
        raise ValueError("invariant_violation:verified_without_stop_blocks_continuation")
    return manifest


def write_level1_rollback_readiness_verification_manifest(*, data_root: str | Path, manifest: dict[str, Any]) -> Path:
    validated = validate_level1_rollback_readiness_verification_manifest(manifest)
    root = Path(data_root).expanduser().resolve()
    verification_id = str(validated["verification_id"])
    manifest_path = root / "atlas" / "level1_rollback_readiness_verifications" / verification_id / "manifest.json"
    _ensure_under(root, manifest_path, "manifest_outside_data_root")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(validated, indent=2, sort_keys=True), encoding="utf-8")
    return manifest_path


def load_level1_rollback_readiness_verification_manifest(*, manifest_path: str | Path, data_root: str | Path | None = None) -> dict[str, Any]:
    path = Path(manifest_path).expanduser().resolve()
    if data_root is not None:
        _ensure_under(Path(data_root).expanduser().resolve(), path, "manifest_outside_data_root")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return validate_level1_rollback_readiness_verification_manifest(payload)


def _evaluate_rollback_readiness_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    missing: list[str] = []
    blocking: list[str] = []
    warnings = _safe_list(manifest.get("warnings"))
    if not manifest:
        missing.append("rollback_readiness_manifest")
        blocking.append("rollback_readiness_manifest_missing")
    if manifest and manifest.get("schema_version") != "atlas.rollback_readiness_gate.v1":
        missing.append("rollback_readiness_schema")
        blocking.append("rollback_readiness_schema_invalid")

    checks = {
        "rollback_ready": manifest.get("rollback_ready") is True,
        "restore_plan_valid": manifest.get("restore_plan_status") == "valid",
        "snapshot_manifest_valid": manifest.get("snapshot_manifest_valid") is True,
        "snapshot_path_safety_valid": manifest.get("snapshot_path_safety_valid") is True,
        "transaction_rollback_metadata_valid": manifest.get("transaction_rollback_metadata_valid") is True,
        "dry_run_gate_ready": manifest.get("dry_run_gate_ready") is True,
        "restore_supported": manifest.get("restore_supported") is True,
        "restore_manual_only": manifest.get("restore_manual_only") is True,
        "automatic_rollback_disabled": manifest.get("automatic_rollback_enabled") is False,
        "automatic_restore_disabled": manifest.get("automatic_restore_enabled") is False,
        "automatic_execute_disabled": manifest.get("automatic_execute_enabled") is False,
        "automatic_safe_apply_disabled": manifest.get("automatic_safe_apply_enabled") is False,
        "automatic_verification_disabled": manifest.get("automatic_verification_enabled") is False,
        "manual_strategy": manifest.get("rollback_strategy") == "restore_snapshot_manual",
    }
    for name, ok in checks.items():
        if not ok:
            missing.append(name)
            blocking.append(f"{name}_required")

    return {
        "rollback_ready": checks["rollback_ready"],
        "rollback_gate_id": _safe_text(manifest.get("rollback_gate_id")),
        "restore_plan_valid": checks["restore_plan_valid"],
        "snapshot_manifest_valid": checks["snapshot_manifest_valid"],
        "snapshot_path_safety_valid": checks["snapshot_path_safety_valid"],
        "transaction_rollback_metadata_valid": checks["transaction_rollback_metadata_valid"],
        "dry_run_gate_ready": checks["dry_run_gate_ready"],
        "restore_supported": checks["restore_supported"],
        "rollback_strategy": _safe_text(manifest.get("rollback_strategy"), "unknown"),
        "risk_level": _safe_text(manifest.get("risk_level"), "unknown"),
        "risk_requires_human_review": bool(manifest.get("risk_requires_human_review")),
        "missing_requirements": missing,
        "blocking_reasons": blocking,
        "warnings": warnings,
    }


def _evaluate_stop_runtime_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    missing: list[str] = []
    blocking: list[str] = []
    warnings: list[str] = []
    if not manifest:
        missing.append("stop_runtime_manifest")
        blocking.append("stop_runtime_manifest_missing")
    else:
        try:
            validate_level1_stop_kill_switch_runtime_manifest(manifest)
        except ValueError as exc:
            missing.append("stop_runtime_manifest_valid")
            blocking.append("stop_runtime_manifest_invalid")
            warnings.append(str(exc))

    stop_verified = bool(manifest) and not blocking and manifest.get("runtime_integration_ready") is True
    stop_blocks = bool(manifest.get("continuation_after_stop_allowed") is False and manifest.get("auto_continue_enabled") is False)
    if not stop_verified:
        missing.append("stop_runtime_integration_ready")
        blocking.append("stop_runtime_integration_not_ready")
    if not stop_blocks:
        missing.append("stop_blocks_continuation")
        blocking.append("stop_blocks_continuation_required")

    return {
        "stop_runtime_integration_verified": stop_verified,
        "stop_runtime_integration_id": _safe_text(manifest.get("runtime_integration_id")),
        "stop_blocks_continuation": stop_blocks,
        "missing_requirements": missing,
        "blocking_reasons": blocking,
        "warnings": warnings,
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _verification_id(*, run_id: str, action_id: str, created_at: str) -> str:
    created_norm = created_at.replace(":", "").replace("-", "").replace("+", "").replace(".", "")
    return f"rollback_verify_{_safe_text(run_id, 'run')}_{_safe_text(action_id, 'action')}_{created_norm}_{uuid.uuid4().hex[:8]}"


def _safe_text(value: Any, fallback: str = "") -> str:
    if isinstance(value, str):
        text = value.strip()
        if text:
            return text[:512]
    return fallback


def _safe_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip()[:512] for item in value if isinstance(item, str) and item.strip()]


def _ensure_under(root: Path, target: Path, code: str) -> Path:
    rr = root.resolve()
    tt = target.resolve()
    if os.path.commonpath([str(rr), str(tt)]) != str(rr):
        raise ValueError(code)
    return tt
