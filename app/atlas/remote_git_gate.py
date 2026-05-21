from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.atlas.artifact_capture_gate import read_artifact_capture_record
from app.atlas.dry_run_approval_gate import read_dry_run_approval_record
from app.atlas.loop_bound_gate import read_loop_bound_record
from app.atlas.risk_classification import read_risk_classification_record
from app.atlas.stop_kill_switch_gate import read_stop_kill_switch_record

SCHEMA_VERSION = "atlas.remote_git_gate.v1"
_FORBIDDEN_OPERATIONS = ["git push", "git pull", "git clone", "git fetch", "git remote", "create branch", "create PR", "draft PR", "merge PR", "direct merge"]
_OPS = {"git_push", "git_pull", "git_clone", "git_fetch", "git_remote", "create_branch", "create_pr", "draft_pr", "merge_pr", "direct_merge"}
_BLOCKED_SNIPPETS = ["git push", "git pull", "git clone", "git fetch", "git remote", "gh pr create", "gh pr merge", "git merge", ";", "&&", "||", "|", ">>", ">", "<", "$(", "`"]

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _ensure_under(root: Path, target: Path, code: str) -> Path:
    rr, tt = root.resolve(), target.resolve()
    if os.path.commonpath([str(rr), str(tt)]) != str(rr):
        raise ValueError(code)
    return tt

def _safe_ref(path_value: str, data_root: Path) -> bool:
    if not path_value:
        return False
    try:
        _ensure_under(data_root, Path(path_value).expanduser().resolve(), "reference_outside_data_root")
    except Exception:
        return False
    return True

def evaluate_remote_git_gate(*, project_path: str | Path, data_root: str | Path | None = None, workspace_id: str = "", pool_id: str = "", item_id: str = "", run_id: str = "", action_id: str = "", reason: str = "", requested_operation: str = "none", requested_command: str = "", requested_remote: str = "", requested_branch: str = "", requested_pr_number: str | int | None = None, requested_repo: str = "", requested_base_branch: str = "", requested_head_branch: str = "", remote_git_operations_enabled: bool = False, git_push_enabled: bool = False, git_pull_enabled: bool = False, git_clone_enabled: bool = False, git_fetch_enabled: bool = False, git_remote_enabled: bool = False, branch_creation_enabled: bool = False, automatic_pr_creation_enabled: bool = False, draft_pr_creation_enabled: bool = False, direct_merge_enabled: bool = False, auto_continue_enabled: bool = False, execute_all_enabled: bool = False, automatic_execute_enabled: bool = False, autonomous_execution_enabled: bool = False, manual_only: bool = True, loop_gate_id: str = "", loop_bound_manifest_path: str = "", stop_gate_id: str = "", stop_gate_manifest_path: str = "", artifact_gate_id: str = "", artifact_capture_manifest_path: str = "", risk_id: str = "", risk_manifest_path: str = "", dry_run_gate_id: str = "", dry_run_gate_manifest_path: str = "", warnings: list[str] | None = None, recovery_instructions: list[str] | None = None, policy_notes: list[str] | None = None) -> dict[str, Any]:
    project_root = Path(project_path).expanduser().resolve()
    root = Path(data_root).expanduser().resolve() if data_root is not None else project_root
    ws = list(warnings or [])
    recovery = list(recovery_instructions or [])
    notes = ["metadata_only_gate", "does_not_run_git_commands", "does_not_create_branches_prs_or_merges", "remote_git_operations_forbidden", "remote_git_gate_ready_does_not_authorize_git_operations"] + list(policy_notes or [])
    blocking_reasons: list[str] = []

    op = (requested_operation or "none").strip().lower()
    requested_operation_forbidden = op in _OPS
    requested_operation_allowed = False
    if requested_operation_forbidden:
        blocking_reasons.append("requested_remote_git_operation_forbidden")

    cmd = (requested_command or "").strip().lower()
    requested_command_present = bool(cmd)
    requested_command_blocked = any(s in cmd for s in _BLOCKED_SNIPPETS)
    if requested_command_blocked:
        blocking_reasons.append("requested_command_contains_forbidden_remote_git_or_shell_pattern")

    flag_pairs = {
        "remote_git_operations_enabled": remote_git_operations_enabled,
        "git_push_enabled": git_push_enabled,
        "git_pull_enabled": git_pull_enabled,
        "git_clone_enabled": git_clone_enabled,
        "git_fetch_enabled": git_fetch_enabled,
        "git_remote_enabled": git_remote_enabled,
        "branch_creation_enabled": branch_creation_enabled,
        "automatic_pr_creation_enabled": automatic_pr_creation_enabled,
        "draft_pr_creation_enabled": draft_pr_creation_enabled,
        "direct_merge_enabled": direct_merge_enabled,
        "auto_continue_enabled": auto_continue_enabled,
        "execute_all_enabled": execute_all_enabled,
        "automatic_execute_enabled": automatic_execute_enabled,
        "autonomous_execution_enabled": autonomous_execution_enabled,
    }
    for k, v in flag_pairs.items():
        if v:
            blocking_reasons.append(f"{k}_forbidden")

    loop_ref = bool(loop_gate_id or loop_bound_manifest_path)
    stop_ref = bool(stop_gate_id or stop_gate_manifest_path)
    artifact_ref = bool(artifact_gate_id or artifact_capture_manifest_path)
    risk_ref = bool(risk_id or risk_manifest_path)
    dry_ref = bool(dry_run_gate_id or dry_run_gate_manifest_path)
    missing_refs = []
    if not loop_ref: missing_refs.append("loop_gate_reference")
    if not stop_ref: missing_refs.append("stop_gate_reference")
    if not artifact_ref: missing_refs.append("artifact_capture_reference")
    if not risk_ref: missing_refs.append("risk_reference")
    if not dry_ref: missing_refs.append("dry_run_gate_reference")
    if missing_refs:
        blocking_reasons.append("missing_required_references")

    for manifest_path, reader, code in [
        (loop_bound_manifest_path, read_loop_bound_record, "loop_ref_unreadable"),
        (stop_gate_manifest_path, read_stop_kill_switch_record, "stop_ref_unreadable"),
        (artifact_capture_manifest_path, read_artifact_capture_record, "artifact_ref_unreadable"),
        (risk_manifest_path, read_risk_classification_record, "risk_ref_unreadable"),
        (dry_run_gate_manifest_path, read_dry_run_approval_record, "dry_run_ref_unreadable"),
    ]:
        if manifest_path:
            if not _safe_ref(manifest_path, root):
                ws.append(code)
                blocking_reasons.append("reference_path_outside_data_root")
            else:
                try:
                    reader(manifest_path=manifest_path, data_root=root)
                except Exception:
                    ws.append(code)
                    blocking_reasons.append("reference_read_failed")

    if not recovery:
        blocking_reasons.append("recovery_instructions_missing")

    ready = (not requested_operation_forbidden and not requested_command_blocked and not missing_refs and not recovery == [] and not any(flag_pairs.values()))
    status = "remote_git_gate_ready_manual_only" if ready else "blocked"

    return {
        "status": status,
        "remote_git_gate_ready": ready,
        "manual_only": True,
        "autonomous_execution_enabled": False,
        "remote_git_operations_enabled": False,
        "git_push_enabled": False,
        "git_pull_enabled": False,
        "git_clone_enabled": False,
        "git_fetch_enabled": False,
        "git_remote_enabled": False,
        "branch_creation_enabled": False,
        "automatic_pr_creation_enabled": False,
        "draft_pr_creation_enabled": False,
        "direct_merge_enabled": False,
        "auto_continue_enabled": False,
        "execute_all_enabled": False,
        "automatic_execute_enabled": False,
        "automatic_command_execution_enabled": False,
        "automatic_safe_apply_enabled": False,
        "automatic_patch_apply_enabled": False,
        "automatic_patch_generation_enabled": False,
        "automatic_rollback_enabled": False,
        "automatic_restore_enabled": False,
        "requested_operation": op,
        "requested_operation_allowed": requested_operation_allowed,
        "requested_operation_forbidden": requested_operation_forbidden,
        "requested_command_present": requested_command_present,
        "requested_command_blocked": requested_command_blocked,
        "loop_gate_reference_present": loop_ref,
        "stop_gate_reference_present": stop_ref,
        "artifact_capture_reference_present": artifact_ref,
        "risk_reference_present": risk_ref,
        "dry_run_gate_reference_present": dry_ref,
        "warnings_present": warnings is not None,
        "recovery_instructions_present": bool(recovery),
        "forbidden_operations": list(_FORBIDDEN_OPERATIONS),
        "missing_required_references": sorted(set(missing_refs)),
        "blocking_reasons": sorted(set(blocking_reasons)),
        "warnings": sorted(set(ws)),
        "policy_notes": notes,
        "remote_git_state_summary": {"requested_operation": op, "requested_command_present": requested_command_present, "requested_command_blocked": requested_command_blocked},
        "summary": {"workspace_id": workspace_id, "pool_id": pool_id, "item_id": item_id, "run_id": run_id, "action_id": action_id, "reason": reason, "manual_only": True},
        "project_path": str(project_root), "data_root": str(root), "workspace_id": workspace_id, "pool_id": pool_id, "item_id": item_id, "run_id": run_id, "action_id": action_id, "reason": reason,
        "requested_command": requested_command, "requested_remote": requested_remote, "requested_branch": requested_branch, "requested_pr_number": requested_pr_number, "requested_repo": requested_repo, "requested_base_branch": requested_base_branch, "requested_head_branch": requested_head_branch,
        "loop_gate_id": loop_gate_id, "loop_bound_manifest_path": loop_bound_manifest_path, "stop_gate_id": stop_gate_id, "stop_gate_manifest_path": stop_gate_manifest_path, "artifact_gate_id": artifact_gate_id, "artifact_capture_manifest_path": artifact_capture_manifest_path, "risk_id": risk_id, "risk_manifest_path": risk_manifest_path, "dry_run_gate_id": dry_run_gate_id, "dry_run_gate_manifest_path": dry_run_gate_manifest_path, "recovery_instructions": recovery,
    }

def create_remote_git_record(*, data_root: str | Path, dry_run: bool = False, **kwargs: Any) -> dict[str, Any]:
    root = Path(data_root).expanduser().resolve()
    gate = kwargs if "remote_git_gate_ready" in kwargs else evaluate_remote_git_gate(data_root=root, **kwargs)
    gid = f"remote_git_gate_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    gdir = root / "atlas" / "remote_git_gates" / gid
    manifest_path = gdir / "manifest.json"
    _ensure_under(root, manifest_path, "manifest_outside_data_root")
    manifest = {"schema_version": SCHEMA_VERSION, "remote_git_gate_id": gid, "created_at": _utc_now(), **gate}
    if not dry_run:
        gdir.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"status": "planned" if dry_run else "created", "remote_git_gate_id": gid, "gate_dir": str(gdir), "manifest_path": str(manifest_path), "manifest": manifest, "dry_run": dry_run}

def read_remote_git_record(*, manifest_path: str | Path | None = None, remote_git_gate_id: str = "", data_root: str | Path | None = None) -> dict[str, Any]:
    mpath = Path(manifest_path).resolve() if manifest_path else Path(data_root).resolve() / "atlas" / "remote_git_gates" / remote_git_gate_id / "manifest.json"
    payload = json.loads(mpath.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported_schema_version")
    root = Path(data_root if data_root is not None else payload.get("data_root", "")).resolve()
    _ensure_under(root, mpath, "manifest_outside_data_root")
    return {"manifest": payload, "warnings": []}

def summarize_remote_git_record(*, manifest_path: str | Path | None = None, remote_git_gate_id: str = "", data_root: str | Path | None = None) -> dict[str, Any]:
    m = read_remote_git_record(manifest_path=manifest_path, remote_git_gate_id=remote_git_gate_id, data_root=data_root)["manifest"]
    return {"remote_git_gate_id": m.get("remote_git_gate_id", ""), "status": m.get("status", "unknown"), "remote_git_gate_ready": bool(m.get("remote_git_gate_ready", False)), "manual_only": True, "blocking_reasons": list(m.get("blocking_reasons", []))}
