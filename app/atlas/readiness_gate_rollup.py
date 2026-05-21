from __future__ import annotations

import json, os, uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "atlas.readiness_gate_rollup.v1"

REQ_GATES = {
    "snapshot": "workspace snapshot / restore foundation",
    "transaction": "patch transaction / rollback metadata foundation",
    "risk": "risk classification gate",
    "allowlist": "verification allowlist gate",
    "dry_run_gate": "dry-run approval gate",
    "rollback_readiness": "rollback readiness gate",
    "artifact_capture": "artifact capture gate",
    "stop_gate": "stop / kill switch gate",
    "loop_bound": "loop bound gate",
    "remote_git": "remote git gate",
    "self_improvement": "self-improvement gate",
}

UNSAFE_FLAGS = ["level1_execution_enabled","autonomous_execution_enabled","autonomous_self_improvement_enabled","automatic_execute_enabled","automatic_command_execution_enabled","automatic_verification_enabled","automatic_patch_generation_enabled","automatic_patch_apply_enabled","automatic_safe_apply_enabled","automatic_rollback_enabled","automatic_restore_enabled","automatic_loop_enabled","automatic_retry_enabled","auto_continue_enabled","execute_all_enabled","remote_git_operations_enabled","direct_merge_enabled"]


def _utc_now() -> str: return datetime.now(timezone.utc).isoformat()

def _ensure_under(root: Path, target: Path, code: str) -> Path:
    rr, tt = root.resolve(), target.resolve()
    if os.path.commonpath([str(rr), str(tt)]) != str(rr): raise ValueError(code)
    return tt


def evaluate_readiness_gate_rollup(*, project_path: str | Path, data_root: str | Path | None = None, workspace_id: str = "", pool_id: str = "", item_id: str = "", run_id: str = "", action_id: str = "", reason: str = "", snapshot_id: str = "", snapshot_manifest_path: str = "", transaction_id: str = "", transaction_manifest_path: str = "", risk_id: str = "", risk_manifest_path: str = "", allowlist_id: str = "", allowlist_manifest_path: str = "", dry_run_gate_id: str = "", dry_run_gate_manifest_path: str = "", rollback_gate_id: str = "", rollback_readiness_manifest_path: str = "", artifact_gate_id: str = "", artifact_capture_manifest_path: str = "", stop_gate_id: str = "", stop_gate_manifest_path: str = "", loop_gate_id: str = "", loop_bound_manifest_path: str = "", remote_git_gate_id: str = "", remote_git_manifest_path: str = "", self_improvement_gate_id: str = "", self_improvement_manifest_path: str = "", snapshot_ready: bool = False, patch_transaction_ready: bool = False, risk_classification_ready: bool = False, verification_allowlist_ready: bool = False, dry_run_approval_ready: bool = False, rollback_readiness_ready: bool = False, artifact_capture_ready: bool = False, stop_kill_switch_ready: bool = False, loop_bound_ready: bool = False, remote_git_gate_ready: bool = False, self_improvement_gate_ready: bool = False, runtime_level: str = "level_0_manual_only", level0_foundation_complete: bool | None = None, manual_only: bool = True, vue_next_allowed_after_pr92: bool = True, vue_next_started: bool = False, vue_next_default_enabled: bool = False, vue_next_execution_enabled: bool = False, warnings: list[str] | None = None, recovery_instructions: list[str] | None = None, policy_notes: list[str] | None = None, **kwargs: Any) -> dict[str, Any]:
    project_root = Path(project_path).expanduser().resolve()
    root = Path(data_root).expanduser().resolve() if data_root is not None else project_root
    ws, recovery = list(warnings or []), list(recovery_instructions or [])
    notes = ["metadata_only_rollup", "readiness_rollup_does_not_authorize_execution"] + list(policy_notes or [])

    refs = {
        "snapshot": bool(snapshot_id or snapshot_manifest_path), "transaction": bool(transaction_id or transaction_manifest_path), "risk": bool(risk_id or risk_manifest_path), "allowlist": bool(allowlist_id or allowlist_manifest_path), "dry_run_gate": bool(dry_run_gate_id or dry_run_gate_manifest_path), "rollback_readiness": bool(rollback_gate_id or rollback_readiness_manifest_path), "artifact_capture": bool(artifact_gate_id or artifact_capture_manifest_path), "stop_gate": bool(stop_gate_id or stop_gate_manifest_path), "loop_bound": bool(loop_gate_id or loop_bound_manifest_path), "remote_git": bool(remote_git_gate_id or remote_git_manifest_path), "self_improvement": bool(self_improvement_gate_id or self_improvement_manifest_path),
    }
    gate_ready = {"snapshot": bool(snapshot_ready), "transaction": bool(patch_transaction_ready), "risk": bool(risk_classification_ready), "allowlist": bool(verification_allowlist_ready), "dry_run_gate": bool(dry_run_approval_ready), "rollback_readiness": bool(rollback_readiness_ready), "artifact_capture": bool(artifact_capture_ready), "stop_gate": bool(stop_kill_switch_ready), "loop_bound": bool(loop_bound_ready), "remote_git": bool(remote_git_gate_ready), "self_improvement": bool(self_improvement_gate_ready)}
    missing = sorted([REQ_GATES[k] for k, v in refs.items() if not v])
    failed = sorted([REQ_GATES[k] for k, v in gate_ready.items() if not v])

    blocks: list[str] = []
    if runtime_level != "level_0_manual_only": blocks.append("runtime_level_not_level_0_manual_only")
    if not manual_only: blocks.append("manual_only_must_be_true")
    unsafe = sorted([k for k in UNSAFE_FLAGS if bool(kwargs.get(k, False))])
    if unsafe: blocks.append("unsafe_automation_flags_present")
    if missing: blocks.append("missing_required_gates")
    if failed: blocks.append("failed_required_gates")
    if not recovery: blocks.append("recovery_instructions_missing")
    if vue_next_started: blocks.append("vue_next_started_not_allowed_in_pr92")
    if vue_next_default_enabled: blocks.append("vue_next_default_enabled_not_allowed")
    if vue_next_execution_enabled: blocks.append("vue_next_execution_enabled_not_allowed")

    for mp in [snapshot_manifest_path, transaction_manifest_path, risk_manifest_path, allowlist_manifest_path, dry_run_gate_manifest_path, rollback_readiness_manifest_path, artifact_capture_manifest_path, stop_gate_manifest_path, loop_bound_manifest_path, remote_git_manifest_path, self_improvement_manifest_path]:
        if not mp: continue
        p = Path(mp).expanduser().resolve()
        try:
            _ensure_under(root, p, "reference_path_outside_data_root")
            if not p.exists():
                ws.append(f"reference_read_failed:{mp}")
                blocks.append("reference_read_failed")
        except ValueError:
            ws.append(f"reference_read_failed:{mp}")
            blocks.append("reference_path_outside_data_root")

    ready = not blocks
    level0_complete = bool(ready)
    status = "level0_readiness_complete_manual_only" if ready else "blocked"
    return {
        "status": status, "readiness_rollup_ready": ready, "level0_foundation_complete": level0_complete,
        "runtime_level": "level_0_manual_only", "manual_only": True,
        **{k: False for k in UNSAFE_FLAGS},
        "snapshot_reference_present": refs["snapshot"], "transaction_reference_present": refs["transaction"], "risk_reference_present": refs["risk"], "allowlist_reference_present": refs["allowlist"], "dry_run_gate_reference_present": refs["dry_run_gate"], "rollback_readiness_reference_present": refs["rollback_readiness"], "artifact_capture_reference_present": refs["artifact_capture"], "stop_gate_reference_present": refs["stop_gate"], "loop_bound_reference_present": refs["loop_bound"], "remote_git_reference_present": refs["remote_git"], "self_improvement_reference_present": refs["self_improvement"],
        "snapshot_ready": gate_ready["snapshot"], "patch_transaction_ready": gate_ready["transaction"], "risk_classification_ready": gate_ready["risk"], "verification_allowlist_ready": gate_ready["allowlist"], "dry_run_approval_ready": gate_ready["dry_run_gate"], "rollback_readiness_ready": gate_ready["rollback_readiness"], "artifact_capture_ready": gate_ready["artifact_capture"], "stop_kill_switch_ready": gate_ready["stop_gate"], "loop_bound_ready": gate_ready["loop_bound"], "remote_git_gate_ready": gate_ready["remote_git"], "self_improvement_gate_ready": gate_ready["self_improvement"],
        "vue_next_allowed_after_pr92": True, "vue_next_started": False, "vue_next_default_enabled": False, "vue_next_execution_enabled": False,
        "required_level0_gates": list(REQ_GATES.values()), "missing_required_gates": missing, "failed_required_gates": failed,
        "unsafe_automation_flags": unsafe, "blocking_reasons": sorted(set(blocks)), "warnings": sorted(set(ws)), "policy_notes": notes,
        "level0_state_summary": {"required_gate_count": len(REQ_GATES), "present_gate_count": sum(1 for v in refs.values() if v), "ready_gate_count": sum(1 for v in gate_ready.values() if v)},
        "summary": {"workspace_id": workspace_id, "pool_id": pool_id, "item_id": item_id, "run_id": run_id, "action_id": action_id, "reason": reason, "manual_only": True},
        "project_path": str(project_root), "data_root": str(root), "workspace_id": workspace_id, "pool_id": pool_id, "item_id": item_id, "run_id": run_id, "action_id": action_id, "reason": reason,
        "snapshot_id": snapshot_id, "snapshot_manifest_path": snapshot_manifest_path, "transaction_id": transaction_id, "transaction_manifest_path": transaction_manifest_path, "risk_id": risk_id, "risk_manifest_path": risk_manifest_path, "allowlist_id": allowlist_id, "allowlist_manifest_path": allowlist_manifest_path, "dry_run_gate_id": dry_run_gate_id, "dry_run_gate_manifest_path": dry_run_gate_manifest_path, "rollback_gate_id": rollback_gate_id, "rollback_readiness_manifest_path": rollback_readiness_manifest_path, "artifact_gate_id": artifact_gate_id, "artifact_capture_manifest_path": artifact_capture_manifest_path, "stop_gate_id": stop_gate_id, "stop_gate_manifest_path": stop_gate_manifest_path, "loop_gate_id": loop_gate_id, "loop_bound_manifest_path": loop_bound_manifest_path, "remote_git_gate_id": remote_git_gate_id, "remote_git_manifest_path": remote_git_manifest_path, "self_improvement_gate_id": self_improvement_gate_id, "self_improvement_manifest_path": self_improvement_manifest_path,
        "recovery_instructions": recovery,
    }


def create_readiness_gate_rollup_record(*, data_root: str | Path, dry_run: bool = False, **kwargs: Any) -> dict[str, Any]:
    root = Path(data_root).expanduser().resolve()
    gate = kwargs if "readiness_rollup_ready" in kwargs else evaluate_readiness_gate_rollup(data_root=root, **kwargs)
    rid = f"readiness_rollup_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    d = root / "atlas" / "readiness_gate_rollups" / rid
    mpath = d / "manifest.json"
    _ensure_under(root, mpath, "manifest_outside_data_root")
    manifest = {"schema_version": SCHEMA_VERSION, "readiness_rollup_id": rid, "created_at": _utc_now(), **gate}
    if not dry_run:
        d.mkdir(parents=True, exist_ok=True)
        mpath.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"status": "planned" if dry_run else "created", "readiness_rollup_id": rid, "gate_dir": str(d), "manifest_path": str(mpath), "manifest": manifest, "dry_run": dry_run}


def read_readiness_gate_rollup_record(*, manifest_path: str | Path | None = None, readiness_rollup_id: str = "", data_root: str | Path | None = None) -> dict[str, Any]:
    mpath = Path(manifest_path).resolve() if manifest_path else Path(data_root).resolve() / "atlas" / "readiness_gate_rollups" / readiness_rollup_id / "manifest.json"
    payload = json.loads(mpath.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION: raise ValueError("unsupported_schema_version")
    root = Path(data_root if data_root is not None else payload.get("data_root", "")).resolve()
    _ensure_under(root, mpath, "manifest_outside_data_root")
    return {"manifest": payload, "warnings": []}


def summarize_readiness_gate_rollup_record(*, manifest_path: str | Path | None = None, readiness_rollup_id: str = "", data_root: str | Path | None = None) -> dict[str, Any]:
    m = read_readiness_gate_rollup_record(manifest_path=manifest_path, readiness_rollup_id=readiness_rollup_id, data_root=data_root)["manifest"]
    return {"readiness_rollup_id": m.get("readiness_rollup_id", ""), "status": m.get("status", "unknown"), "readiness_rollup_ready": bool(m.get("readiness_rollup_ready", False)), "level0_foundation_complete": bool(m.get("level0_foundation_complete", False)), "runtime_level": m.get("runtime_level", "level_0_manual_only"), "blocking_reasons": list(m.get("blocking_reasons", []))}
