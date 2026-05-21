from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "atlas.stop_kill_switch_gate.v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_under(root: Path, target: Path, code: str) -> Path:
    rr = root.resolve()
    tt = target.resolve()
    if os.path.commonpath([str(rr), str(tt)]) != str(rr):
        raise ValueError(code)
    return tt


def evaluate_stop_kill_switch_gate(*, project_path: str | Path, workspace_id: str = "", pool_id: str = "", item_id: str = "", run_id: str = "", action_id: str = "", reason: str = "", stop_state: str = "unknown", stop_requested: bool = False, stop_request_id: str = "", stop_requested_at: str = "", stop_requested_by: str = "", stop_reason: str = "", stop_source: str = "unknown", stop_acknowledged: bool = False, stop_acknowledged_at: str = "", stop_acknowledged_by: str = "", stop_acknowledgement_id: str = "", kill_switch_available: bool = False, stop_state_visible: bool = False, ui_stop_visible: bool = False, cli_stop_available: bool = False, api_stop_available: bool = False, operator_loop_stop_visible: bool = False, current_phase: str = "", current_status: str = "", last_heartbeat_at: str = "", running_action_count: int = 0, pending_action_count: int = 0, auto_continue_enabled: bool = False, execute_all_enabled: bool = False, automatic_execute_enabled: bool = False, automatic_retry_enabled: bool = False, automatic_rollback_enabled: bool = False, autonomous_execution_enabled: bool = False, manual_only: bool = True, artifact_gate_id: str = "", artifact_capture_manifest_path: str = "", dry_run_gate_id: str = "", dry_run_gate_manifest_path: str = "", rollback_gate_id: str = "", rollback_readiness_manifest_path: str = "", stop_log_path: str = "", warnings: list[str] | None = None, recovery_instructions: list[str] | None = None, policy_notes: list[str] | None = None, data_root: str | Path | None = None) -> dict[str, Any]:
    project_root = Path(project_path).expanduser().resolve()
    root = Path(data_root).expanduser().resolve() if data_root is not None else project_root

    ws = list(warnings or [])
    notes = [
        "metadata_only_gate",
        "does_not_stop_jobs",
        "does_not_kill_processes",
        "does_not_execute_actions",
        "does_not_run_verification",
    ] + list(policy_notes or [])

    required_stop_controls = ["kill_switch_available", "stop_state_visible", "ui_stop_visible", "cli_stop_available", "api_stop_available", "operator_loop_stop_visible"]
    checks = {
        "kill_switch_available": bool(kill_switch_available),
        "stop_state_visible": bool(stop_state_visible),
        "ui_stop_visible": bool(ui_stop_visible),
        "cli_stop_available": bool(cli_stop_available),
        "api_stop_available": bool(api_stop_available),
        "operator_loop_stop_visible": bool(operator_loop_stop_visible),
        "artifact_capture_reference": bool(artifact_gate_id or artifact_capture_manifest_path),
        "recovery_instructions": bool(recovery_instructions),
    }
    missing_controls = [k for k in required_stop_controls if not checks[k]]
    missing_evidence = []
    if not checks["artifact_capture_reference"]:
        missing_evidence.append("artifact_capture_reference")
    if not checks["recovery_instructions"]:
        missing_evidence.append("recovery_instructions")

    blocking_reasons = [f"{x}_missing" for x in missing_controls] + [f"{x}_missing" for x in missing_evidence]
    if auto_continue_enabled:
        blocking_reasons.append("auto_continue_enabled_forbidden")
    if execute_all_enabled:
        blocking_reasons.append("execute_all_enabled_forbidden")
    if automatic_execute_enabled:
        blocking_reasons.append("automatic_execute_enabled_forbidden")
    if autonomous_execution_enabled:
        blocking_reasons.append("autonomous_execution_enabled_forbidden")
    if stop_acknowledged and not (stop_requested or stop_request_id):
        blocking_reasons.append("inconsistent_stop_acknowledged_without_request")
        ws.append("stop_acknowledged_without_stop_requested_or_stop_request_id")

    stop_state_summary = {
        "stop_state": stop_state,
        "stop_requested": bool(stop_requested),
        "stop_acknowledged": bool(stop_acknowledged),
        "running_action_count": int(running_action_count or 0),
        "pending_action_count": int(pending_action_count or 0),
    }

    stop_gate_ready = len(blocking_reasons) == 0
    if stop_acknowledged:
        status = "stop_acknowledged_manual_halt"
    elif stop_requested:
        status = "stop_requested_manual_halt"
    elif stop_gate_ready:
        status = "stop_gate_ready_manual_only"
    else:
        status = "blocked"

    return {
        "status": status,
        "stop_gate_ready": stop_gate_ready,
        "stop_requested": bool(stop_requested),
        "stop_acknowledged": bool(stop_acknowledged),
        "manual_only": True,
        "autonomous_execution_enabled": False,
        "auto_continue_enabled": False,
        "execute_all_enabled": False,
        "automatic_execute_enabled": False,
        "automatic_retry_enabled": False,
        "automatic_rollback_enabled": False,
        "automatic_restore_enabled": False,
        "automatic_safe_apply_enabled": False,
        "automatic_verification_enabled": False,
        "automatic_command_execution_enabled": False,
        "automatic_stop_execution_enabled": False,
        "kill_switch_available": bool(kill_switch_available),
        "stop_state_visible": bool(stop_state_visible),
        "ui_stop_visible": bool(ui_stop_visible),
        "cli_stop_available": bool(cli_stop_available),
        "api_stop_available": bool(api_stop_available),
        "operator_loop_stop_visible": bool(operator_loop_stop_visible),
        "artifact_capture_reference_present": bool(artifact_gate_id or artifact_capture_manifest_path),
        "dry_run_gate_reference_present": bool(dry_run_gate_id or dry_run_gate_manifest_path),
        "rollback_readiness_reference_present": bool(rollback_gate_id or rollback_readiness_manifest_path),
        "stop_log_reference_present": bool(stop_log_path),
        "warnings_present": warnings is not None,
        "recovery_instructions_present": bool(recovery_instructions),
        "required_stop_controls": required_stop_controls,
        "missing_stop_controls": sorted(set(missing_controls)),
        "missing_required_evidence": sorted(set(missing_evidence)),
        "blocking_reasons": sorted(set(blocking_reasons)),
        "warnings": sorted(set(ws)),
        "policy_notes": notes,
        "stop_state_summary": stop_state_summary,
        "summary": {"workspace_id": workspace_id, "pool_id": pool_id, "item_id": item_id, "run_id": run_id, "action_id": action_id, "reason": reason, "manual_only": True},
        "project_path": str(project_root),
        "data_root": str(root),
        "stop_state": stop_state,
        "stop_request_id": stop_request_id,
        "stop_requested_at": stop_requested_at,
        "stop_requested_by": stop_requested_by,
        "stop_reason": stop_reason,
        "stop_source": stop_source,
        "stop_acknowledged_at": stop_acknowledged_at,
        "stop_acknowledged_by": stop_acknowledged_by,
        "stop_acknowledgement_id": stop_acknowledgement_id,
        "current_phase": current_phase,
        "current_status": current_status,
        "last_heartbeat_at": last_heartbeat_at,
        "running_action_count": int(running_action_count or 0),
        "pending_action_count": int(pending_action_count or 0),
        "artifact_gate_id": artifact_gate_id,
        "artifact_capture_manifest_path": artifact_capture_manifest_path,
        "dry_run_gate_id": dry_run_gate_id,
        "dry_run_gate_manifest_path": dry_run_gate_manifest_path,
        "rollback_gate_id": rollback_gate_id,
        "rollback_readiness_manifest_path": rollback_readiness_manifest_path,
        "stop_log_path": stop_log_path,
        "recovery_instructions": list(recovery_instructions or []),
    }


def create_stop_kill_switch_record(*, data_root: str | Path, dry_run: bool = False, **kwargs: Any) -> dict[str, Any]:
    root = Path(data_root).expanduser().resolve()
    gate = kwargs if "stop_gate_ready" in kwargs else evaluate_stop_kill_switch_gate(data_root=root, **kwargs)
    gid = f"stop_gate_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    gdir = root / "atlas" / "stop_kill_switch_gates" / gid
    manifest_path = gdir / "manifest.json"
    _ensure_under(root, manifest_path, "manifest_outside_data_root")
    m = {"schema_version": SCHEMA_VERSION, "stop_gate_id": gid, "created_at": _utc_now(), **gate}
    if not dry_run:
        gdir.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(m, indent=2), encoding="utf-8")
    return {"status": "planned" if dry_run else "created", "stop_gate_id": gid, "gate_dir": str(gdir), "manifest_path": str(manifest_path), "manifest": m, "dry_run": dry_run}


def read_stop_kill_switch_record(*, manifest_path: str | Path | None = None, stop_gate_id: str = "", data_root: str | Path | None = None) -> dict[str, Any]:
    mpath = Path(manifest_path).resolve() if manifest_path else Path(data_root).resolve() / "atlas" / "stop_kill_switch_gates" / stop_gate_id / "manifest.json"
    payload = json.loads(mpath.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported_schema_version")
    root = Path(data_root if data_root is not None else payload.get("data_root", "")).resolve()
    _ensure_under(root, mpath, "manifest_outside_data_root")
    return {"manifest": payload, "warnings": []}


def summarize_stop_kill_switch_record(*, manifest_path: str | Path | None = None, stop_gate_id: str = "", data_root: str | Path | None = None) -> dict[str, Any]:
    m = read_stop_kill_switch_record(manifest_path=manifest_path, stop_gate_id=stop_gate_id, data_root=data_root)["manifest"]
    return {"stop_gate_id": m.get("stop_gate_id", ""), "status": m.get("status", "unknown"), "stop_gate_ready": bool(m.get("stop_gate_ready", False)), "manual_only": True, "missing_stop_controls": list(m.get("missing_stop_controls", [])), "blocking_reasons": list(m.get("blocking_reasons", [])), "missing_required_evidence": list(m.get("missing_required_evidence", []))}
