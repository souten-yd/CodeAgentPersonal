from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from app.atlas.artifact_capture_gate import read_artifact_capture_record
from app.atlas.dry_run_approval_gate import read_dry_run_approval_record
from app.atlas.loop_bound_gate import read_loop_bound_record
from app.atlas.patch_transaction import read_patch_transaction_manifest
from app.atlas.remote_git_gate import read_remote_git_record
from app.atlas.risk_classification import read_risk_classification_record
from app.atlas.rollback_readiness_gate import read_rollback_readiness_record
from app.atlas.stop_kill_switch_gate import read_stop_kill_switch_record
from app.atlas.verification_allowlist import read_verification_allowlist_record
from app.atlas.workspace_snapshot import read_workspace_snapshot_manifest

SCHEMA_VERSION = "atlas.self_improvement_gate.v1"
_KIND = {"none", "docs_only", "tests_only", "ui_contract", "agent_runtime", "execution_policy", "autonomous_loop", "self_modification", "unknown"}
_RISK = {"low", "medium", "high", "strict_gate", "unknown"}
_STRICT_PREFIX = ("app/api/", "app/atlas/", "agent/", ".github/workflows/")
_STRICT_EXACT = {
    "main.py", "start.bat", "start.sh", "dockerfile", "pyproject.toml", "package.json", "web/js/atlas_dashboard.js",
    "web/js/atlas_pipeline_api.js", "web/atlas_ui_surface_manifest.json", "ui.html", "docs/atlas_autonomous_execution_readiness_policy.md",
    "docs/atlas_development_constitution.md", "docs/atlas_self_development_rules.md", "docs/atlas_preflight_checklist.md", "docs/atlas_postflight_checklist.md",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_under(root: Path, target: Path, code: str) -> Path:
    rr, tt = root.resolve(), target.resolve()
    if os.path.commonpath([str(rr), str(tt)]) != str(rr):
        raise ValueError(code)
    return tt


def _safe_rel(path_value: str) -> str:
    p = PurePosixPath(path_value.replace("\\", "/"))
    if p.is_absolute():
        raise ValueError("target_path_absolute_forbidden")
    if any(part in ("", ".", "..") for part in p.parts):
        raise ValueError("target_path_traversal_forbidden")
    return p.as_posix()


def _strict_path(rel: str) -> bool:
    l = rel.lower()
    if l in _STRICT_EXACT or any(l.startswith(x) for x in _STRICT_PREFIX):
        return True
    if l.startswith("requirements") and l.endswith(".txt"):
        return True
    if l.startswith("docker-compose"):
        return True
    if l.startswith("tests/") and ("safety" in l or "autonomous" in l or "quality_gate" in l):
        return True
    return False


def evaluate_self_improvement_gate(*, project_path: str | Path, data_root: str | Path | None = None, workspace_id: str = "", pool_id: str = "", item_id: str = "", run_id: str = "", action_id: str = "", reason: str = "", self_improvement_requested: bool = False, self_improvement_kind: str = "none", target_paths: list[str] | None = None, touches_agent_runtime: bool = False, touches_execution_semantics: bool = False, touches_safety_policy: bool = False, touches_autonomous_controls: bool = False, touches_remote_git_policy: bool = False, touches_model_runtime: bool = False, touches_data_root: bool = False, touches_ui_workflow_state: bool = False, touches_tests_for_safety_gates: bool = False, snapshot_id: str = "", snapshot_manifest_path: str = "", transaction_id: str = "", transaction_manifest_path: str = "", risk_id: str = "", risk_manifest_path: str = "", allowlist_id: str = "", allowlist_manifest_path: str = "", dry_run_gate_id: str = "", dry_run_gate_manifest_path: str = "", rollback_gate_id: str = "", rollback_readiness_manifest_path: str = "", artifact_gate_id: str = "", artifact_capture_manifest_path: str = "", stop_gate_id: str = "", stop_gate_manifest_path: str = "", loop_gate_id: str = "", loop_bound_manifest_path: str = "", remote_git_gate_id: str = "", remote_git_manifest_path: str = "", risk_level: str = "unknown", strict_gate_required: bool | None = None, strict_gate_satisfied: bool = False, human_approval_required: bool | None = None, human_approval_present: bool = False, dry_run_satisfied: bool = False, rollback_ready: bool = False, artifact_capture_ready: bool = False, stop_gate_ready: bool = False, loop_bound_ready: bool = False, remote_git_gate_ready: bool = False, verification_allowlist_ready: bool = False, autonomous_execution_enabled: bool = False, autonomous_self_improvement_enabled: bool = False, automatic_self_modification_enabled: bool = False, automatic_patch_generation_enabled: bool = False, automatic_patch_apply_enabled: bool = False, automatic_safe_apply_enabled: bool = False, automatic_verification_enabled: bool = False, automatic_command_execution_enabled: bool = False, automatic_rollback_enabled: bool = False, automatic_restore_enabled: bool = False, automatic_loop_enabled: bool = False, automatic_retry_enabled: bool = False, auto_continue_enabled: bool = False, execute_all_enabled: bool = False, remote_git_operations_enabled: bool = False, automatic_pr_creation_enabled: bool = False, direct_merge_enabled: bool = False, manual_only: bool = True, warnings: list[str] | None = None, recovery_instructions: list[str] | None = None, policy_notes: list[str] | None = None) -> dict[str, Any]:
    project_root = Path(project_path).expanduser().resolve()
    root = Path(data_root).expanduser().resolve() if data_root is not None else project_root
    ws = list(warnings or [])
    recovery = list(recovery_instructions or [])
    notes = ["metadata_only_gate", "no_execution_authorized", "no_patch_apply", "no_git_operations_authorized"] + list(policy_notes or [])
    blocks: list[str] = []
    strict_reasons: list[str] = []

    scope_known = self_improvement_kind in _KIND and self_improvement_kind != "unknown"
    if not scope_known:
        blocks.append("self_improvement_kind_unknown")
    if risk_level not in _RISK or risk_level == "unknown":
        blocks.append("risk_level_unknown")

    safe_paths = True
    strict_touch = False
    norm_targets: list[str] = []
    for p in target_paths or []:
        try:
            rel = _safe_rel(p)
            norm_targets.append(rel)
            if _strict_path(rel):
                strict_touch = True
        except ValueError as exc:
            safe_paths = False
            blocks.append(str(exc))
    if not safe_paths:
        blocks.append("target_paths_unsafe")

    if self_improvement_kind == "self_modification": strict_reasons.append("self_modification_kind")
    for cond, reason_code in [
        (touches_agent_runtime, "touches_agent_runtime"), (touches_execution_semantics, "touches_execution_semantics"),
        (touches_safety_policy, "touches_safety_policy"), (touches_autonomous_controls, "touches_autonomous_controls"),
        (touches_remote_git_policy, "touches_remote_git_policy"), (touches_data_root, "touches_data_root"), (touches_ui_workflow_state, "touches_ui_workflow_state"),
        (touches_tests_for_safety_gates, "touches_tests_for_safety_gates"), (strict_touch, "target_path_strict_gate_pattern")
    ]:
        if cond: strict_reasons.append(reason_code)

    strict_required = bool(strict_reasons) if strict_gate_required is None else bool(strict_gate_required or strict_reasons)
    approval_required = strict_required if human_approval_required is None else bool(human_approval_required or strict_required)
    strict_ok = bool(strict_gate_satisfied and (not approval_required or human_approval_present))
    if strict_required and not human_approval_present: blocks.append("human_approval_missing")
    if strict_required and not strict_gate_satisfied: blocks.append("strict_gate_not_satisfied")

    refs = {
        "snapshot_reference": bool(snapshot_id or snapshot_manifest_path), "transaction_reference": bool(transaction_id or transaction_manifest_path),
        "risk_reference": bool(risk_id or risk_manifest_path), "allowlist_reference": bool(allowlist_id or allowlist_manifest_path),
        "dry_run_gate_reference": bool(dry_run_gate_id or dry_run_gate_manifest_path), "rollback_readiness_reference": bool(rollback_gate_id or rollback_readiness_manifest_path),
        "artifact_capture_reference": bool(artifact_gate_id or artifact_capture_manifest_path), "stop_gate_reference": bool(stop_gate_id or stop_gate_manifest_path),
        "loop_bound_reference": bool(loop_gate_id or loop_bound_manifest_path), "remote_git_reference": bool(remote_git_gate_id or remote_git_manifest_path),
    }
    missing = [k for k, v in refs.items() if not v]
    if missing: blocks.append("missing_required_gates")

    for mp, reader in [
        (snapshot_manifest_path, read_workspace_snapshot_manifest), (transaction_manifest_path, read_patch_transaction_manifest),
        (risk_manifest_path, read_risk_classification_record), (allowlist_manifest_path, read_verification_allowlist_record),
        (dry_run_gate_manifest_path, read_dry_run_approval_record), (rollback_readiness_manifest_path, read_rollback_readiness_record),
        (artifact_capture_manifest_path, read_artifact_capture_record), (stop_gate_manifest_path, read_stop_kill_switch_record),
        (loop_bound_manifest_path, read_loop_bound_record), (remote_git_manifest_path, read_remote_git_record),
    ]:
        if mp:
            try:
                _ensure_under(root, Path(mp).expanduser().resolve(), "reference_path_outside_data_root")
            except ValueError:
                blocks.append("reference_path_outside_data_root")
                ws.append(f"reference_read_failed:{mp}")
                continue
            try:
                reader(manifest_path=mp, data_root=root)
            except Exception:
                ws.append(f"reference_read_failed:{mp}")
                blocks.append("reference_read_failed")

    if not dry_run_satisfied: blocks.append("dry_run_not_satisfied")
    if not rollback_ready: blocks.append("rollback_not_ready")
    if not artifact_capture_ready: blocks.append("artifact_capture_not_ready")
    if not stop_gate_ready: blocks.append("stop_gate_not_ready")
    if not loop_bound_ready: blocks.append("loop_bound_not_ready")
    if not remote_git_gate_ready: blocks.append("remote_git_gate_not_ready")
    if not verification_allowlist_ready: blocks.append("verification_allowlist_not_ready")
    if not recovery: blocks.append("recovery_instructions_missing")

    flags = {k: v for k, v in {
        "autonomous_execution_enabled": autonomous_execution_enabled, "autonomous_self_improvement_enabled": autonomous_self_improvement_enabled,
        "automatic_self_modification_enabled": automatic_self_modification_enabled, "automatic_patch_generation_enabled": automatic_patch_generation_enabled,
        "automatic_patch_apply_enabled": automatic_patch_apply_enabled, "automatic_safe_apply_enabled": automatic_safe_apply_enabled,
        "automatic_verification_enabled": automatic_verification_enabled, "automatic_command_execution_enabled": automatic_command_execution_enabled,
        "automatic_rollback_enabled": automatic_rollback_enabled, "automatic_restore_enabled": automatic_restore_enabled,
        "automatic_loop_enabled": automatic_loop_enabled, "automatic_retry_enabled": automatic_retry_enabled,
        "auto_continue_enabled": auto_continue_enabled, "execute_all_enabled": execute_all_enabled, "remote_git_operations_enabled": remote_git_operations_enabled,
        "automatic_pr_creation_enabled": automatic_pr_creation_enabled, "direct_merge_enabled": direct_merge_enabled,
    }.items() if v}
    if flags: blocks.append("unsafe_automation_flags_present")

    ready = not blocks
    status = "self_improvement_gate_ready_manual_only" if ready else ("manual_review_required" if not self_improvement_requested else "blocked")
    return {
        "status": status, "self_improvement_gate_ready": ready, "self_improvement_requested": bool(self_improvement_requested), "self_improvement_scope_known": scope_known,
        "target_paths_safe": safe_paths, "touches_strict_gate_area": strict_touch, "strict_gate_required": strict_required, "strict_gate_satisfied": strict_ok,
        "human_approval_required": approval_required, "human_approval_present": bool(human_approval_present),
        "snapshot_reference_present": refs["snapshot_reference"], "transaction_reference_present": refs["transaction_reference"], "risk_reference_present": refs["risk_reference"],
        "allowlist_reference_present": refs["allowlist_reference"], "dry_run_gate_reference_present": refs["dry_run_gate_reference"], "rollback_readiness_reference_present": refs["rollback_readiness_reference"],
        "artifact_capture_reference_present": refs["artifact_capture_reference"], "stop_gate_reference_present": refs["stop_gate_reference"], "loop_bound_reference_present": refs["loop_bound_reference"],
        "remote_git_reference_present": refs["remote_git_reference"], "warnings_present": bool(ws), "recovery_instructions_present": bool(recovery),
        "dry_run_satisfied": bool(dry_run_satisfied), "rollback_ready": bool(rollback_ready), "artifact_capture_ready": bool(artifact_capture_ready), "stop_gate_ready": bool(stop_gate_ready),
        "loop_bound_ready": bool(loop_bound_ready), "remote_git_gate_ready": bool(remote_git_gate_ready), "verification_allowlist_ready": bool(verification_allowlist_ready),
        "required_self_improvement_gates": list(refs.keys()), "missing_required_gates": missing, "unsafe_automation_flags": sorted(flags.keys()),
        "strict_gate_reasons": sorted(set(strict_reasons)), "blocking_reasons": sorted(set(blocks)), "warnings": sorted(set(ws)), "policy_notes": notes,
        "self_improvement_state_summary": {"kind": self_improvement_kind, "requested": bool(self_improvement_requested), "target_paths": norm_targets},
        "summary": {"workspace_id": workspace_id, "pool_id": pool_id, "item_id": item_id, "run_id": run_id, "action_id": action_id, "reason": reason, "manual_only": True},
        "project_path": str(project_root), "data_root": str(root), "workspace_id": workspace_id, "pool_id": pool_id, "item_id": item_id, "run_id": run_id, "action_id": action_id, "reason": reason,
        "self_improvement_kind": self_improvement_kind, "target_paths": norm_targets, "touches_agent_runtime": touches_agent_runtime, "touches_execution_semantics": touches_execution_semantics,
        "touches_safety_policy": touches_safety_policy, "touches_autonomous_controls": touches_autonomous_controls, "touches_remote_git_policy": touches_remote_git_policy,
        "touches_model_runtime": touches_model_runtime, "touches_data_root": touches_data_root, "touches_ui_workflow_state": touches_ui_workflow_state, "touches_tests_for_safety_gates": touches_tests_for_safety_gates,
        "snapshot_id": snapshot_id, "snapshot_manifest_path": snapshot_manifest_path, "transaction_id": transaction_id, "transaction_manifest_path": transaction_manifest_path,
        "risk_id": risk_id, "risk_manifest_path": risk_manifest_path, "allowlist_id": allowlist_id, "allowlist_manifest_path": allowlist_manifest_path,
        "dry_run_gate_id": dry_run_gate_id, "dry_run_gate_manifest_path": dry_run_gate_manifest_path, "rollback_gate_id": rollback_gate_id,
        "rollback_readiness_manifest_path": rollback_readiness_manifest_path, "artifact_gate_id": artifact_gate_id, "artifact_capture_manifest_path": artifact_capture_manifest_path,
        "stop_gate_id": stop_gate_id, "stop_gate_manifest_path": stop_gate_manifest_path, "loop_gate_id": loop_gate_id, "loop_bound_manifest_path": loop_bound_manifest_path,
        "remote_git_gate_id": remote_git_gate_id, "remote_git_manifest_path": remote_git_manifest_path, "risk_level": risk_level, "recovery_instructions": recovery,
        "manual_only": True, "autonomous_execution_enabled": False, "autonomous_self_improvement_enabled": False, "automatic_self_modification_enabled": False,
        "automatic_patch_generation_enabled": False, "automatic_patch_apply_enabled": False, "automatic_safe_apply_enabled": False, "automatic_verification_enabled": False,
        "automatic_command_execution_enabled": False, "automatic_rollback_enabled": False, "automatic_restore_enabled": False, "automatic_loop_enabled": False,
        "automatic_retry_enabled": False, "auto_continue_enabled": False, "execute_all_enabled": False, "remote_git_operations_enabled": False,
        "automatic_pr_creation_enabled": False, "direct_merge_enabled": False,
    }


def create_self_improvement_record(*, data_root: str | Path, dry_run: bool = False, **kwargs: Any) -> dict[str, Any]:
    root = Path(data_root).expanduser().resolve()
    if "self_improvement_gate_ready" in kwargs:
        gate = dict(kwargs)
        gate["data_root"] = str(root)
        if "project_path" in gate:
            gate["project_path"] = str(Path(gate["project_path"]).expanduser().resolve())
    else:
        gate = evaluate_self_improvement_gate(data_root=root, **kwargs)
    gid = f"self_improvement_gate_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    gdir = root / "atlas" / "self_improvement_gates" / gid
    manifest_path = gdir / "manifest.json"
    _ensure_under(root, manifest_path, "manifest_outside_data_root")
    manifest = {"schema_version": SCHEMA_VERSION, "self_improvement_gate_id": gid, "created_at": _utc_now(), **gate}
    if not dry_run:
        gdir.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"status": "planned" if dry_run else "created", "self_improvement_gate_id": gid, "gate_dir": str(gdir), "manifest_path": str(manifest_path), "manifest": manifest, "dry_run": dry_run}


def read_self_improvement_record(*, manifest_path: str | Path | None = None, self_improvement_gate_id: str = "", data_root: str | Path | None = None) -> dict[str, Any]:
    mpath = Path(manifest_path).resolve() if manifest_path else Path(data_root).resolve() / "atlas" / "self_improvement_gates" / self_improvement_gate_id / "manifest.json"
    payload = json.loads(mpath.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported_schema_version")
    root = Path(data_root if data_root is not None else payload.get("data_root", "")).resolve()
    _ensure_under(root, mpath, "manifest_outside_data_root")
    return {"manifest": payload, "warnings": []}


def summarize_self_improvement_record(*, manifest_path: str | Path | None = None, self_improvement_gate_id: str = "", data_root: str | Path | None = None) -> dict[str, Any]:
    m = read_self_improvement_record(manifest_path=manifest_path, self_improvement_gate_id=self_improvement_gate_id, data_root=data_root)["manifest"]
    return {"self_improvement_gate_id": m.get("self_improvement_gate_id", ""), "status": m.get("status", "unknown"), "self_improvement_gate_ready": bool(m.get("self_improvement_gate_ready", False)), "manual_only": True, "blocking_reasons": list(m.get("blocking_reasons", []))}
