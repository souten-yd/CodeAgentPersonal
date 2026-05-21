from __future__ import annotations

import json
import math
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "atlas.loop_bound_gate.v1"
_RISK_ORDER = {"low": 1, "medium": 2, "high": 3, "strict_gate": 4, "unknown": 0}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_under(root: Path, target: Path, code: str) -> Path:
    rr = root.resolve()
    tt = target.resolve()
    if os.path.commonpath([str(rr), str(tt)]) != str(rr):
        raise ValueError(code)
    return tt


def _finite_int(v: Any) -> bool:
    return isinstance(v, int) and math.isfinite(v)


def _ok_bound(v: Any, *, min_value: int) -> bool:
    return _finite_int(v) and int(v) >= min_value


def evaluate_loop_bound_gate(*, project_path: str | Path, data_root: str | Path | None = None, workspace_id: str = "", pool_id: str = "", item_id: str = "", run_id: str = "", action_id: str = "", reason: str = "", loop_mode: str = "unknown", loop_state: str = "unknown", current_action_count: int = 0, current_retry_count: int = 0, current_runtime_seconds: int = 0, current_changed_file_count: int = 0, current_consecutive_failure_count: int = 0, current_verification_attempt_count: int = 0, current_patch_transaction_count: int = 0, current_risk_level: str = "unknown", max_actions_per_loop: int | None = None, max_retries: int | None = None, max_runtime_seconds: int | None = None, max_files_changed: int | None = None, max_consecutive_failures: int | None = None, max_verification_attempts: int | None = None, max_patch_transactions: int | None = None, max_risk_level: str = "unknown", stop_gate_id: str = "", stop_gate_manifest_path: str = "", artifact_gate_id: str = "", artifact_capture_manifest_path: str = "", dry_run_gate_id: str = "", dry_run_gate_manifest_path: str = "", rollback_gate_id: str = "", rollback_readiness_manifest_path: str = "", risk_id: str = "", risk_manifest_path: str = "", loop_bounds_configured: bool | None = None, stop_gate_ready: bool = False, stop_requested: bool = False, stop_acknowledged: bool = False, auto_continue_enabled: bool = False, execute_all_enabled: bool = False, automatic_loop_enabled: bool = False, automatic_retry_enabled: bool = False, automatic_execute_enabled: bool = False, automatic_verification_enabled: bool = False, automatic_rollback_enabled: bool = False, autonomous_execution_enabled: bool = False, manual_only: bool = True, warnings: list[str] | None = None, recovery_instructions: list[str] | None = None, policy_notes: list[str] | None = None) -> dict[str, Any]:
    project_root = Path(project_path).expanduser().resolve()
    root = Path(data_root).expanduser().resolve() if data_root is not None else project_root

    ws = list(warnings or [])
    recovery = list(recovery_instructions or [])
    notes = [
        "metadata_only_gate",
        "does_not_run_loops",
        "does_not_execute_actions",
        "does_not_retry_automatically",
        "does_not_continue_automatically",
        "does_not_authorize_automatic_execution",
    ] + list(policy_notes or [])

    required_bounds = ["max_actions_per_loop", "max_retries", "max_runtime_seconds", "max_files_changed", "max_consecutive_failures", "max_verification_attempts", "max_patch_transactions", "max_risk_level"]
    missing_bounds: list[str] = []
    exceeded_bounds: list[str] = []
    blocking_reasons: list[str] = []

    if not _ok_bound(max_actions_per_loop, min_value=1):
        missing_bounds.append("max_actions_per_loop")
    if not _ok_bound(max_retries, min_value=0):
        missing_bounds.append("max_retries")
    if not _ok_bound(max_runtime_seconds, min_value=1):
        missing_bounds.append("max_runtime_seconds")
    if not _ok_bound(max_files_changed, min_value=0):
        missing_bounds.append("max_files_changed")
    if not _ok_bound(max_consecutive_failures, min_value=0):
        missing_bounds.append("max_consecutive_failures")
    if not _ok_bound(max_verification_attempts, min_value=0):
        missing_bounds.append("max_verification_attempts")
    if not _ok_bound(max_patch_transactions, min_value=0):
        missing_bounds.append("max_patch_transactions")
    if max_risk_level not in {"low", "medium", "high", "strict_gate"}:
        missing_bounds.append("max_risk_level")

    if _ok_bound(max_actions_per_loop, min_value=1) and int(current_action_count or 0) > int(max_actions_per_loop):
        exceeded_bounds.append("max_actions_per_loop")
    if _ok_bound(max_retries, min_value=0) and int(current_retry_count or 0) > int(max_retries):
        exceeded_bounds.append("max_retries")
    if _ok_bound(max_runtime_seconds, min_value=1) and int(current_runtime_seconds or 0) > int(max_runtime_seconds):
        exceeded_bounds.append("max_runtime_seconds")
    if _ok_bound(max_files_changed, min_value=0) and int(current_changed_file_count or 0) > int(max_files_changed):
        exceeded_bounds.append("max_files_changed")
    if _ok_bound(max_consecutive_failures, min_value=0) and int(current_consecutive_failure_count or 0) > int(max_consecutive_failures):
        exceeded_bounds.append("max_consecutive_failures")
    if _ok_bound(max_verification_attempts, min_value=0) and int(current_verification_attempt_count or 0) > int(max_verification_attempts):
        exceeded_bounds.append("max_verification_attempts")
    if _ok_bound(max_patch_transactions, min_value=0) and int(current_patch_transaction_count or 0) > int(max_patch_transactions):
        exceeded_bounds.append("max_patch_transactions")

    if current_risk_level == "unknown" or current_risk_level not in _RISK_ORDER:
        exceeded_bounds.append("max_risk_level")
        ws.append("current_risk_level_unknown_or_invalid")
    elif max_risk_level in _RISK_ORDER and _RISK_ORDER[current_risk_level] > _RISK_ORDER[max_risk_level]:
        exceeded_bounds.append("max_risk_level")

    refs = {
        "stop_gate_reference": bool(stop_gate_id or stop_gate_manifest_path),
        "artifact_capture_reference": bool(artifact_gate_id or artifact_capture_manifest_path),
        "dry_run_gate_reference": bool(dry_run_gate_id or dry_run_gate_manifest_path),
        "rollback_readiness_reference": bool(rollback_gate_id or rollback_readiness_manifest_path),
        "risk_reference": bool(risk_id or risk_manifest_path),
    }
    missing_required_references = [k for k, v in refs.items() if not v]
    if stop_requested:
        blocking_reasons.append("stop_requested_manual_halt")
    if auto_continue_enabled:
        blocking_reasons.append("auto_continue_enabled_forbidden")
    if execute_all_enabled:
        blocking_reasons.append("execute_all_enabled_forbidden")
    if automatic_loop_enabled:
        blocking_reasons.append("automatic_loop_enabled_forbidden")
    if automatic_retry_enabled:
        blocking_reasons.append("automatic_retry_enabled_forbidden")
    if automatic_execute_enabled:
        blocking_reasons.append("automatic_execute_enabled_forbidden")
    if automatic_verification_enabled:
        blocking_reasons.append("automatic_verification_enabled_forbidden")
    if automatic_rollback_enabled:
        blocking_reasons.append("automatic_rollback_enabled_forbidden")
    if autonomous_execution_enabled:
        blocking_reasons.append("autonomous_execution_enabled_forbidden")
    if not recovery:
        blocking_reasons.append("recovery_instructions_missing")
    if missing_bounds:
        blocking_reasons.append("missing_required_bounds")
    if exceeded_bounds:
        blocking_reasons.append("bounds_exceeded")
    if missing_required_references:
        blocking_reasons.append("missing_required_references")

    bounds_configured = bool(loop_bounds_configured) if loop_bounds_configured is not None else (len(missing_bounds) == 0)
    max_actions_satisfied = "max_actions_per_loop" not in exceeded_bounds and "max_actions_per_loop" not in missing_bounds
    max_retries_satisfied = "max_retries" not in exceeded_bounds and "max_retries" not in missing_bounds
    max_runtime_satisfied = "max_runtime_seconds" not in exceeded_bounds and "max_runtime_seconds" not in missing_bounds
    max_files_changed_satisfied = "max_files_changed" not in exceeded_bounds and "max_files_changed" not in missing_bounds
    max_consecutive_failures_satisfied = "max_consecutive_failures" not in exceeded_bounds and "max_consecutive_failures" not in missing_bounds
    max_verification_attempts_satisfied = "max_verification_attempts" not in exceeded_bounds and "max_verification_attempts" not in missing_bounds
    max_patch_transactions_satisfied = "max_patch_transactions" not in exceeded_bounds and "max_patch_transactions" not in missing_bounds
    max_risk_level_satisfied = "max_risk_level" not in exceeded_bounds and "max_risk_level" not in missing_bounds

    loop_bound_ready = bounds_configured and not blocking_reasons
    status = "loop_bound_ready_manual_only" if loop_bound_ready else "blocked"
    if stop_requested:
        status = "stop_requested_manual_halt"

    return {
        "status": status,
        "loop_bound_ready": loop_bound_ready,
        "manual_only": True,
        "autonomous_execution_enabled": False,
        "auto_continue_enabled": False,
        "execute_all_enabled": False,
        "automatic_loop_enabled": False,
        "automatic_retry_enabled": False,
        "automatic_execute_enabled": False,
        "automatic_verification_enabled": False,
        "automatic_command_execution_enabled": False,
        "automatic_safe_apply_enabled": False,
        "automatic_rollback_enabled": False,
        "automatic_restore_enabled": False,
        "loop_bounds_configured": bounds_configured,
        "max_actions_satisfied": max_actions_satisfied,
        "max_retries_satisfied": max_retries_satisfied,
        "max_runtime_satisfied": max_runtime_satisfied,
        "max_files_changed_satisfied": max_files_changed_satisfied,
        "max_consecutive_failures_satisfied": max_consecutive_failures_satisfied,
        "max_verification_attempts_satisfied": max_verification_attempts_satisfied,
        "max_patch_transactions_satisfied": max_patch_transactions_satisfied,
        "max_risk_level_satisfied": max_risk_level_satisfied,
        "stop_gate_reference_present": refs["stop_gate_reference"],
        "artifact_capture_reference_present": refs["artifact_capture_reference"],
        "dry_run_gate_reference_present": refs["dry_run_gate_reference"],
        "rollback_readiness_reference_present": refs["rollback_readiness_reference"],
        "risk_reference_present": refs["risk_reference"],
        "warnings_present": warnings is not None,
        "recovery_instructions_present": bool(recovery),
        "required_bounds": required_bounds,
        "missing_bounds": sorted(set(missing_bounds)),
        "exceeded_bounds": sorted(set(exceeded_bounds)),
        "missing_required_references": sorted(set(missing_required_references)),
        "blocking_reasons": sorted(set(blocking_reasons)),
        "warnings": sorted(set(ws)),
        "policy_notes": notes,
        "loop_state_summary": {"loop_mode": loop_mode, "loop_state": loop_state, "current_action_count": int(current_action_count or 0), "current_retry_count": int(current_retry_count or 0), "current_runtime_seconds": int(current_runtime_seconds or 0), "current_changed_file_count": int(current_changed_file_count or 0), "current_consecutive_failure_count": int(current_consecutive_failure_count or 0), "current_verification_attempt_count": int(current_verification_attempt_count or 0), "current_patch_transaction_count": int(current_patch_transaction_count or 0), "current_risk_level": current_risk_level},
        "summary": {"workspace_id": workspace_id, "pool_id": pool_id, "item_id": item_id, "run_id": run_id, "action_id": action_id, "reason": reason, "manual_only": True},
        "project_path": str(project_root),
        "data_root": str(root),
        "loop_mode": loop_mode,
        "loop_state": loop_state,
        "current_action_count": int(current_action_count or 0),
        "current_retry_count": int(current_retry_count or 0),
        "current_runtime_seconds": int(current_runtime_seconds or 0),
        "current_changed_file_count": int(current_changed_file_count or 0),
        "current_consecutive_failure_count": int(current_consecutive_failure_count or 0),
        "current_verification_attempt_count": int(current_verification_attempt_count or 0),
        "current_patch_transaction_count": int(current_patch_transaction_count or 0),
        "current_risk_level": current_risk_level,
        "max_actions_per_loop": max_actions_per_loop,
        "max_retries": max_retries,
        "max_runtime_seconds": max_runtime_seconds,
        "max_files_changed": max_files_changed,
        "max_consecutive_failures": max_consecutive_failures,
        "max_verification_attempts": max_verification_attempts,
        "max_patch_transactions": max_patch_transactions,
        "max_risk_level": max_risk_level,
        "stop_gate_id": stop_gate_id,
        "stop_gate_manifest_path": stop_gate_manifest_path,
        "artifact_gate_id": artifact_gate_id,
        "artifact_capture_manifest_path": artifact_capture_manifest_path,
        "dry_run_gate_id": dry_run_gate_id,
        "dry_run_gate_manifest_path": dry_run_gate_manifest_path,
        "rollback_gate_id": rollback_gate_id,
        "rollback_readiness_manifest_path": rollback_readiness_manifest_path,
        "risk_id": risk_id,
        "risk_manifest_path": risk_manifest_path,
        "stop_gate_ready": bool(stop_gate_ready),
        "stop_requested": bool(stop_requested),
        "stop_acknowledged": bool(stop_acknowledged),
        "recovery_instructions": recovery,
    }


def create_loop_bound_record(*, data_root: str | Path, dry_run: bool = False, **kwargs: Any) -> dict[str, Any]:
    root = Path(data_root).expanduser().resolve()
    gate = kwargs if "loop_bound_ready" in kwargs else evaluate_loop_bound_gate(data_root=root, **kwargs)
    gid = f"loop_gate_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    gdir = root / "atlas" / "loop_bound_gates" / gid
    manifest_path = gdir / "manifest.json"
    _ensure_under(root, manifest_path, "manifest_outside_data_root")
    manifest = {"schema_version": SCHEMA_VERSION, "loop_gate_id": gid, "created_at": _utc_now(), **gate}
    if not dry_run:
        gdir.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"status": "planned" if dry_run else "created", "loop_gate_id": gid, "gate_dir": str(gdir), "manifest_path": str(manifest_path), "manifest": manifest, "dry_run": dry_run}


def read_loop_bound_record(*, manifest_path: str | Path | None = None, loop_gate_id: str = "", data_root: str | Path | None = None) -> dict[str, Any]:
    mpath = Path(manifest_path).resolve() if manifest_path else Path(data_root).resolve() / "atlas" / "loop_bound_gates" / loop_gate_id / "manifest.json"
    payload = json.loads(mpath.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported_schema_version")
    root = Path(data_root if data_root is not None else payload.get("data_root", "")).resolve()
    _ensure_under(root, mpath, "manifest_outside_data_root")
    return {"manifest": payload, "warnings": []}


def summarize_loop_bound_record(*, manifest_path: str | Path | None = None, loop_gate_id: str = "", data_root: str | Path | None = None) -> dict[str, Any]:
    m = read_loop_bound_record(manifest_path=manifest_path, loop_gate_id=loop_gate_id, data_root=data_root)["manifest"]
    return {"loop_gate_id": m.get("loop_gate_id", ""), "status": m.get("status", "unknown"), "loop_bound_ready": bool(m.get("loop_bound_ready", False)), "manual_only": True, "missing_bounds": list(m.get("missing_bounds", [])), "exceeded_bounds": list(m.get("exceeded_bounds", [])), "blocking_reasons": list(m.get("blocking_reasons", []))}
