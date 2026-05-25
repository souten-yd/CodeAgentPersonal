from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.atlas.dry_run_artifact_schema import validate_dry_run_artifact_manifest
from app.atlas.level1_disabled_command_runner import (
    RUNTIME_LEVEL as LEVEL0_RUNTIME,
)
from app.atlas.level1_execution_artifact_capture import validate_level1_execution_artifact_manifest
from app.atlas.level1_rollback_readiness_verification import (
    validate_level1_rollback_readiness_verification_manifest,
)
from app.atlas.level1_stop_kill_switch_runtime import validate_level1_stop_kill_switch_runtime_manifest

SCHEMA_VERSION = "atlas.level1_guarded_single_step_endpoint_contract.v1"
RUNTIME_LEVEL = "level_0_manual_only"
NEXT_RUNTIME_TRANSITION_PR = "PR-ATLAS-SCALE-127"


def create_level1_guarded_single_step_endpoint_contract(
    *,
    project_path: str | Path,
    data_root: str | Path | None = None,
    workspace_id: str = "default",
    pool_id: str = "",
    item_id: str = "",
    run_id: str = "",
    action_id: str = "",
    requested_command: str = "",
    risk_level: str = "unknown",
    dry_run_artifact_manifest: dict[str, Any] | None = None,
    approval_token_validation: dict[str, Any] | None = None,
    disabled_runner_contract: dict[str, Any] | None = None,
    execution_artifact_manifest: dict[str, Any] | None = None,
    stop_runtime_manifest: dict[str, Any] | None = None,
    rollback_verification_manifest: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    created = created_at or _utc_now()
    project_root = Path(project_path).expanduser().resolve()
    root = Path(data_root).expanduser().resolve() if data_root is not None else project_root

    checks = {
        "dry_run_artifact": _check_dry_run_artifact(dry_run_artifact_manifest or {}),
        "approval_token": _check_approval_token_validation(approval_token_validation or {}),
        "disabled_runner": _check_disabled_runner_contract(disabled_runner_contract or {}),
        "execution_artifact": _check_execution_artifact(execution_artifact_manifest or {}),
        "stop_runtime": _check_stop_runtime(stop_runtime_manifest or {}),
        "rollback_verification": _check_rollback_verification(rollback_verification_manifest or {}),
    }
    missing_requirements: list[str] = []
    blocking_reasons: list[str] = []
    warnings: list[str] = []
    for name, check in checks.items():
        if not check["ok"]:
            missing_requirements.append(name)
            blocking_reasons.extend(check["blocking_reasons"])
        warnings.extend(check["warnings"])

    risk = _safe_text(risk_level, "unknown").lower()
    if risk != "low":
        missing_requirements.append("low_risk_level")
        blocking_reasons.append("only_low_risk_allowed_for_level1_candidate")

    gate_complete = not blocking_reasons
    current_runtime_allows_execution = False
    execution_blocked_until_transition = True

    contract = {
        "schema_version": SCHEMA_VERSION,
        "endpoint_contract_id": _contract_id(run_id=run_id, action_id=action_id, created_at=created),
        "created_at": created,
        "workspace_id": _safe_text(workspace_id, "default"),
        "pool_id": _safe_text(pool_id),
        "item_id": _safe_text(item_id),
        "run_id": _safe_text(run_id, "run"),
        "action_id": _safe_text(action_id, "action"),
        "project_path": str(project_root),
        "data_root": str(root),
        "requested_command": _safe_text(requested_command),
        "risk_level": risk,
        "runtime_level": RUNTIME_LEVEL,
        "target_runtime_level": "level_1_guarded_single_step",
        "next_runtime_transition_pr": NEXT_RUNTIME_TRANSITION_PR,
        "manual_only": True,
        "single_action_only": True,
        "dry_run_required": True,
        "explicit_approval_required": True,
        "rollback_readiness_required": True,
        "stop_gate_required": True,
        "allowlisted_runner_required": True,
        "endpoint_contract_ready": gate_complete,
        "limited_execution_candidate": gate_complete,
        "callable_execution_endpoint_enabled": False,
        "current_runtime_allows_execution": current_runtime_allows_execution,
        "execution_blocked_until_runtime_transition": execution_blocked_until_transition,
        "execution_enabled": False,
        "level1_execution_enabled": False,
        "autonomous_execution_enabled": False,
        "execution_performed": False,
        "mutation_performed": False,
        "verification_performed": False,
        "rollback_performed": False,
        "restore_performed": False,
        "auto_continue_enabled": False,
        "execute_all_enabled": False,
        "backend_authoritative": True,
        "vue_authoritative": False,
        "evidence_checks": checks,
        "missing_requirements": sorted(set(missing_requirements)),
        "blocking_reasons": sorted(set(blocking_reasons + ["runtime_transition_required_before_execution"])),
        "warnings": sorted(set(warnings)),
        "policy_notes": [
            "scale_125_level1_guarded_single_step_endpoint_contract",
            "dry_run_and_approval_required",
            "single_action_only",
            "low_risk_only",
            "no_callable_route_until_runtime_transition",
            "no_execution_performed",
        ],
        "next_required_pr": "PR-ATLAS-SCALE-126",
    }
    return validate_level1_guarded_single_step_endpoint_contract(contract)


def validate_level1_guarded_single_step_endpoint_contract(contract: dict[str, Any]) -> dict[str, Any]:
    required = [
        "schema_version",
        "endpoint_contract_id",
        "runtime_level",
        "manual_only",
        "single_action_only",
        "dry_run_required",
        "explicit_approval_required",
        "callable_execution_endpoint_enabled",
        "current_runtime_allows_execution",
        "execution_blocked_until_runtime_transition",
        "execution_enabled",
        "level1_execution_enabled",
        "autonomous_execution_enabled",
        "execution_performed",
        "mutation_performed",
        "verification_performed",
        "rollback_performed",
        "restore_performed",
        "auto_continue_enabled",
        "execute_all_enabled",
        "backend_authoritative",
        "vue_authoritative",
    ]
    missing = [field for field in required if field not in contract]
    if missing:
        raise ValueError(f"missing_required_fields:{','.join(missing)}")
    invariants = {
        "schema_version": contract.get("schema_version") == SCHEMA_VERSION,
        "runtime_level": contract.get("runtime_level") == RUNTIME_LEVEL,
        "manual_only": contract.get("manual_only") is True,
        "single_action_only": contract.get("single_action_only") is True,
        "dry_run_required": contract.get("dry_run_required") is True,
        "explicit_approval_required": contract.get("explicit_approval_required") is True,
        "callable_execution_endpoint_enabled": contract.get("callable_execution_endpoint_enabled") is False,
        "current_runtime_allows_execution": contract.get("current_runtime_allows_execution") is False,
        "execution_blocked_until_runtime_transition": contract.get("execution_blocked_until_runtime_transition") is True,
        "execution_enabled": contract.get("execution_enabled") is False,
        "level1_execution_enabled": contract.get("level1_execution_enabled") is False,
        "autonomous_execution_enabled": contract.get("autonomous_execution_enabled") is False,
        "execution_performed": contract.get("execution_performed") is False,
        "mutation_performed": contract.get("mutation_performed") is False,
        "verification_performed": contract.get("verification_performed") is False,
        "rollback_performed": contract.get("rollback_performed") is False,
        "restore_performed": contract.get("restore_performed") is False,
        "auto_continue_enabled": contract.get("auto_continue_enabled") is False,
        "execute_all_enabled": contract.get("execute_all_enabled") is False,
        "backend_authoritative": contract.get("backend_authoritative") is True,
        "vue_authoritative": contract.get("vue_authoritative") is False,
    }
    violations = [key for key, ok in invariants.items() if not ok]
    if violations:
        raise ValueError(f"invariant_violation:{','.join(sorted(violations))}")
    return contract


def write_level1_guarded_single_step_endpoint_contract(*, data_root: str | Path, contract: dict[str, Any]) -> Path:
    validated = validate_level1_guarded_single_step_endpoint_contract(contract)
    root = Path(data_root).expanduser().resolve()
    endpoint_contract_id = str(validated["endpoint_contract_id"])
    manifest_path = root / "atlas" / "level1_guarded_single_step_endpoint_contracts" / endpoint_contract_id / "manifest.json"
    _ensure_under(root, manifest_path, "manifest_outside_data_root")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(validated, indent=2, sort_keys=True), encoding="utf-8")
    return manifest_path


def load_level1_guarded_single_step_endpoint_contract(*, manifest_path: str | Path, data_root: str | Path | None = None) -> dict[str, Any]:
    path = Path(manifest_path).expanduser().resolve()
    if data_root is not None:
        _ensure_under(Path(data_root).expanduser().resolve(), path, "manifest_outside_data_root")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return validate_level1_guarded_single_step_endpoint_contract(payload)


def _check_dry_run_artifact(manifest: dict[str, Any]) -> dict[str, Any]:
    return _validator_check(
        manifest,
        missing_reason="dry_run_artifact_missing",
        invalid_prefix="dry_run_artifact_invalid",
        validator=validate_dry_run_artifact_manifest,
    )


def _check_approval_token_validation(validation: dict[str, Any]) -> dict[str, Any]:
    required = {
        "approval_token_valid": True,
        "token_digest_matches": True,
        "confirmation_text_satisfied": True,
        "dry_run_artifact_present": True,
        "runtime_level_ok": True,
        "no_execution_authority": True,
        "execution_authorized": False,
        "autonomous_loop_authorized": False,
        "mutation_authorized": False,
    }
    return _field_check(validation, required, missing_reason="approval_token_validation_missing")


def _check_disabled_runner_contract(contract: dict[str, Any]) -> dict[str, Any]:
    required = {
        "runtime_level": LEVEL0_RUNTIME,
        "manual_only": True,
        "single_action_only": True,
        "dry_run_required": True,
        "explicit_approval_required": True,
        "runner_enabled": False,
        "execution_supported": False,
        "execution_performed": False,
        "mutation_performed": False,
        "level1_execution_enabled": False,
        "autonomous_execution_enabled": False,
    }
    return _field_check(contract, required, missing_reason="disabled_runner_contract_missing")


def _check_execution_artifact(manifest: dict[str, Any]) -> dict[str, Any]:
    return _validator_check(
        manifest,
        missing_reason="execution_artifact_missing",
        invalid_prefix="execution_artifact_invalid",
        validator=validate_level1_execution_artifact_manifest,
    )


def _check_stop_runtime(manifest: dict[str, Any]) -> dict[str, Any]:
    base = _validator_check(
        manifest,
        missing_reason="stop_runtime_manifest_missing",
        invalid_prefix="stop_runtime_manifest_invalid",
        validator=validate_level1_stop_kill_switch_runtime_manifest,
    )
    if base["ok"] and manifest.get("runtime_integration_ready") is not True:
        base["ok"] = False
        base["blocking_reasons"].append("stop_runtime_integration_not_ready")
    return base


def _check_rollback_verification(manifest: dict[str, Any]) -> dict[str, Any]:
    base = _validator_check(
        manifest,
        missing_reason="rollback_verification_manifest_missing",
        invalid_prefix="rollback_verification_manifest_invalid",
        validator=validate_level1_rollback_readiness_verification_manifest,
    )
    if base["ok"] and manifest.get("rollback_readiness_verified") is not True:
        base["ok"] = False
        base["blocking_reasons"].append("rollback_readiness_not_verified")
    return base


def _validator_check(manifest: dict[str, Any], *, missing_reason: str, invalid_prefix: str, validator) -> dict[str, Any]:
    if not manifest:
        return {"ok": False, "blocking_reasons": [missing_reason], "warnings": []}
    try:
        validator(manifest)
        return {"ok": True, "blocking_reasons": [], "warnings": []}
    except ValueError as exc:
        return {"ok": False, "blocking_reasons": [invalid_prefix], "warnings": [str(exc)]}


def _field_check(payload: dict[str, Any], required: dict[str, Any], *, missing_reason: str) -> dict[str, Any]:
    if not payload:
        return {"ok": False, "blocking_reasons": [missing_reason], "warnings": []}
    failures = [field for field, expected in required.items() if payload.get(field) != expected]
    return {
        "ok": not failures,
        "blocking_reasons": [f"{field}_required" for field in failures],
        "warnings": [],
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _contract_id(*, run_id: str, action_id: str, created_at: str) -> str:
    created_norm = created_at.replace(":", "").replace("-", "").replace("+", "").replace(".", "")
    return f"level1_endpoint_{_safe_text(run_id, 'run')}_{_safe_text(action_id, 'action')}_{created_norm}_{uuid.uuid4().hex[:8]}"


def _safe_text(value: Any, fallback: str = "") -> str:
    if isinstance(value, str):
        text = value.strip()
        if text:
            return text[:512]
    return fallback


def _ensure_under(root: Path, target: Path, code: str) -> Path:
    rr = root.resolve()
    tt = target.resolve()
    if os.path.commonpath([str(rr), str(tt)]) != str(rr):
        raise ValueError(code)
    return tt
