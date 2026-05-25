from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "atlas.level1_runtime_transition_checkpoint.v1"
TRANSITION_PR = "PR-ATLAS-SCALE-127"
PREVIOUS_RUNTIME_LEVEL = "level_0_manual_only"
RUNTIME_LEVEL = "level_1_guarded_single_step"
NEXT_REQUIRED_PR = "PR-ATLAS-SCALE-128"


def create_level1_runtime_transition_checkpoint(
    *,
    project_path: str | Path,
    data_root: str | Path | None = None,
    readiness_rollup: dict[str, Any],
    endpoint_contract: dict[str, Any],
    workspace_id: str = "default",
    pool_id: str = "",
    item_id: str = "",
    run_id: str = "",
    action_id: str = "",
    created_at: str | None = None,
) -> dict[str, Any]:
    created = created_at or _utc_now()
    project_root = Path(project_path).expanduser().resolve()
    root = Path(data_root).expanduser().resolve() if data_root is not None else project_root

    checks = {
        "readiness_rollup": _check_readiness_rollup(readiness_rollup),
        "endpoint_contract": _check_endpoint_contract(endpoint_contract),
    }
    blocking_reasons: list[str] = []
    for check in checks.values():
        blocking_reasons.extend(check["blocking_reasons"])

    transition_authorized = not blocking_reasons
    checkpoint = {
        "schema_version": SCHEMA_VERSION,
        "checkpoint_id": _checkpoint_id(run_id=run_id, action_id=action_id, created_at=created),
        "created_at": created,
        "transition_pr": TRANSITION_PR,
        "next_required_pr": NEXT_REQUIRED_PR,
        "workspace_id": _safe_text(workspace_id, "default"),
        "pool_id": _safe_text(pool_id),
        "item_id": _safe_text(item_id),
        "run_id": _safe_text(run_id, "run"),
        "action_id": _safe_text(action_id, "action"),
        "project_path": str(project_root),
        "data_root": str(root),
        "previous_runtime_level": PREVIOUS_RUNTIME_LEVEL,
        "runtime_level": RUNTIME_LEVEL,
        "target_runtime_level": RUNTIME_LEVEL,
        "transition_authorized": transition_authorized,
        "transition_blocked": not transition_authorized,
        "level1_execution_enabled": transition_authorized,
        "level1_single_step_execution_allowed": transition_authorized,
        "callable_execution_endpoint_policy_enabled": transition_authorized,
        "public_execution_route_added": False,
        "dry_run_required": True,
        "explicit_approval_required": True,
        "single_action_only": True,
        "low_risk_only": True,
        "stop_gate_required": True,
        "rollback_readiness_required": True,
        "backend_authoritative": True,
        "vue_authoritative": False,
        "vue_execution_controls_enabled": False,
        "autonomous_execution_enabled": False,
        "self_modification_enabled": False,
        "auto_continue_enabled": False,
        "execute_all_enabled": False,
        "patch_apply_enabled": False,
        "rollback_auto_restore_enabled": False,
        "remote_git_operations_enabled": False,
        "execution_performed": False,
        "mutation_performed": False,
        "verification_performed": False,
        "rollback_performed": False,
        "restore_performed": False,
        "gate_checks": checks,
        "blocking_reasons": sorted(set(blocking_reasons)),
        "policy_notes": [
            "scale_127_explicit_level1_runtime_transition_checkpoint",
            "one_low_risk_allowlisted_action_only",
            "dry_run_and_explicit_approval_required",
            "no_auto_continue",
            "no_autonomous_loop",
            "no_patch_apply_or_remote_git",
            "vue_remains_non_authoritative",
        ],
    }
    return validate_level1_runtime_transition_checkpoint(checkpoint)


def validate_level1_runtime_transition_checkpoint(checkpoint: dict[str, Any]) -> dict[str, Any]:
    required = [
        "schema_version",
        "transition_pr",
        "previous_runtime_level",
        "runtime_level",
        "transition_authorized",
        "level1_execution_enabled",
        "level1_single_step_execution_allowed",
        "callable_execution_endpoint_policy_enabled",
        "public_execution_route_added",
        "dry_run_required",
        "explicit_approval_required",
        "single_action_only",
        "low_risk_only",
        "stop_gate_required",
        "rollback_readiness_required",
        "backend_authoritative",
        "vue_authoritative",
        "vue_execution_controls_enabled",
        "autonomous_execution_enabled",
        "self_modification_enabled",
        "auto_continue_enabled",
        "execute_all_enabled",
        "patch_apply_enabled",
        "rollback_auto_restore_enabled",
        "remote_git_operations_enabled",
        "execution_performed",
        "mutation_performed",
        "verification_performed",
        "rollback_performed",
        "restore_performed",
    ]
    missing = [field for field in required if field not in checkpoint]
    if missing:
        raise ValueError(f"missing_required_fields:{','.join(missing)}")

    transition_authorized = bool(checkpoint.get("transition_authorized"))
    invariants = {
        "schema_version": checkpoint.get("schema_version") == SCHEMA_VERSION,
        "transition_pr": checkpoint.get("transition_pr") == TRANSITION_PR,
        "previous_runtime_level": checkpoint.get("previous_runtime_level") == PREVIOUS_RUNTIME_LEVEL,
        "runtime_level": checkpoint.get("runtime_level") == RUNTIME_LEVEL,
        "transition_blocked": checkpoint.get("transition_blocked") is (not transition_authorized),
        "level1_execution_enabled": checkpoint.get("level1_execution_enabled") is transition_authorized,
        "level1_single_step_execution_allowed": checkpoint.get("level1_single_step_execution_allowed") is transition_authorized,
        "callable_execution_endpoint_policy_enabled": checkpoint.get("callable_execution_endpoint_policy_enabled") is transition_authorized,
        "public_execution_route_added": checkpoint.get("public_execution_route_added") is False,
        "dry_run_required": checkpoint.get("dry_run_required") is True,
        "explicit_approval_required": checkpoint.get("explicit_approval_required") is True,
        "single_action_only": checkpoint.get("single_action_only") is True,
        "low_risk_only": checkpoint.get("low_risk_only") is True,
        "stop_gate_required": checkpoint.get("stop_gate_required") is True,
        "rollback_readiness_required": checkpoint.get("rollback_readiness_required") is True,
        "backend_authoritative": checkpoint.get("backend_authoritative") is True,
        "vue_authoritative": checkpoint.get("vue_authoritative") is False,
        "vue_execution_controls_enabled": checkpoint.get("vue_execution_controls_enabled") is False,
        "autonomous_execution_enabled": checkpoint.get("autonomous_execution_enabled") is False,
        "self_modification_enabled": checkpoint.get("self_modification_enabled") is False,
        "auto_continue_enabled": checkpoint.get("auto_continue_enabled") is False,
        "execute_all_enabled": checkpoint.get("execute_all_enabled") is False,
        "patch_apply_enabled": checkpoint.get("patch_apply_enabled") is False,
        "rollback_auto_restore_enabled": checkpoint.get("rollback_auto_restore_enabled") is False,
        "remote_git_operations_enabled": checkpoint.get("remote_git_operations_enabled") is False,
        "execution_performed": checkpoint.get("execution_performed") is False,
        "mutation_performed": checkpoint.get("mutation_performed") is False,
        "verification_performed": checkpoint.get("verification_performed") is False,
        "rollback_performed": checkpoint.get("rollback_performed") is False,
        "restore_performed": checkpoint.get("restore_performed") is False,
    }
    violations = [key for key, ok in invariants.items() if not ok]
    if violations:
        raise ValueError(f"invariant_violation:{','.join(sorted(violations))}")
    return checkpoint


def write_level1_runtime_transition_checkpoint(*, data_root: str | Path, checkpoint: dict[str, Any]) -> Path:
    validated = validate_level1_runtime_transition_checkpoint(checkpoint)
    root = Path(data_root).expanduser().resolve()
    checkpoint_id = str(validated["checkpoint_id"])
    path = root / "atlas" / "level1_runtime_transition_checkpoints" / checkpoint_id / "manifest.json"
    _ensure_under(root, path, "manifest_outside_data_root")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(validated, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_level1_runtime_transition_checkpoint(*, manifest_path: str | Path, data_root: str | Path | None = None) -> dict[str, Any]:
    path = Path(manifest_path).expanduser().resolve()
    if data_root is not None:
        _ensure_under(Path(data_root).expanduser().resolve(), path, "manifest_outside_data_root")
    return validate_level1_runtime_transition_checkpoint(json.loads(path.read_text(encoding="utf-8")))


def _check_readiness_rollup(rollup: dict[str, Any]) -> dict[str, Any]:
    required = {
        "readiness_rollup_ready": True,
        "level0_foundation_complete": True,
        "runtime_level": PREVIOUS_RUNTIME_LEVEL,
        "manual_only": True,
        "execution_enabled": False,
        "level1_execution_enabled": False,
        "autonomous_execution_enabled": False,
        "auto_continue_enabled": False,
        "execute_all_enabled": False,
        "remote_git_operations_enabled": False,
    }
    return _field_check(rollup, required, missing_reason="readiness_rollup_missing")


def _check_endpoint_contract(contract: dict[str, Any]) -> dict[str, Any]:
    required = {
        "endpoint_contract_ready": True,
        "limited_execution_candidate": True,
        "runtime_level": PREVIOUS_RUNTIME_LEVEL,
        "target_runtime_level": RUNTIME_LEVEL,
        "next_runtime_transition_pr": TRANSITION_PR,
        "single_action_only": True,
        "dry_run_required": True,
        "explicit_approval_required": True,
        "rollback_readiness_required": True,
        "stop_gate_required": True,
        "allowlisted_runner_required": True,
        "current_runtime_allows_execution": False,
        "execution_blocked_until_runtime_transition": True,
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
    }
    return _field_check(contract, required, missing_reason="endpoint_contract_missing")


def _field_check(payload: dict[str, Any], required: dict[str, Any], *, missing_reason: str) -> dict[str, Any]:
    if not payload:
        return {"ok": False, "blocking_reasons": [missing_reason]}
    failures = [field for field, expected in required.items() if payload.get(field) != expected]
    return {"ok": not failures, "blocking_reasons": [f"{field}_required" for field in failures]}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _checkpoint_id(*, run_id: str, action_id: str, created_at: str) -> str:
    created_norm = created_at.replace(":", "").replace("-", "").replace("+", "").replace(".", "")
    return f"level1_transition_{_safe_text(run_id, 'run')}_{_safe_text(action_id, 'action')}_{created_norm}_{uuid.uuid4().hex[:8]}"


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
