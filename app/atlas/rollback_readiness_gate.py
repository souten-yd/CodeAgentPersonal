from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "atlas.rollback_readiness_gate.v1"
_VALID_RESTORE_PLAN = {"missing", "planned", "valid", "invalid", "unknown"}
_KNOWN_RISK_LEVELS = {"low", "medium", "high", "strict_gate"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_under(root: Path, target: Path, code: str) -> Path:
    rr = root.resolve()
    tt = target.resolve()
    if os.path.commonpath([str(rr), str(tt)]) != str(rr):
        raise ValueError(code)
    return tt


def evaluate_rollback_readiness_gate(*, project_path: str | Path, workspace_id: str = "", pool_id: str = "", item_id: str = "", run_id: str = "", action_id: str = "", reason: str = "", risk_level: str = "unknown", risk_id: str = "", risk_manifest_path: str = "", transaction_id: str = "", transaction_manifest_path: str = "", snapshot_id: str = "", snapshot_manifest_path: str = "", restore_plan_status: str = "unknown", restore_plan_id: str = "", restore_supported: bool = False, restore_manual_only: bool = True, rollback_metadata_present: bool = False, rollback_strategy: str = "", snapshot_manifest_valid: bool = False, snapshot_path_safety_valid: bool = False, transaction_rollback_metadata_valid: bool = False, dry_run_gate_id: str = "", dry_run_gate_manifest_path: str = "", dry_run_gate_ready: bool = False, allowlist_id: str = "", allowlist_manifest_path: str = "", manual_only: bool = True) -> dict[str, Any]:
    project_root = Path(project_path).expanduser().resolve()
    missing: list[str] = []
    blocked: list[str] = []
    warnings: list[str] = []
    policy_notes = [
        "metadata_only_gate",
        "rollback_readiness_does_not_execute_rollback",
        "restore_manual_only",
        "automatic_rollback_disabled",
    ]

    snapshot_ref = bool(snapshot_id or snapshot_manifest_path)
    txn_ref = bool(transaction_id or transaction_manifest_path)
    dry_ref = bool(dry_run_gate_id or dry_run_gate_manifest_path)

    if not snapshot_ref:
        missing.append("snapshot_reference_required")
        blocked.append("snapshot_reference_missing")
    if snapshot_ref and not snapshot_manifest_valid:
        missing.append("snapshot_manifest_valid_required")
        blocked.append("snapshot_manifest_invalid")
    if snapshot_ref and not snapshot_path_safety_valid:
        missing.append("snapshot_path_safety_required")
        blocked.append("snapshot_path_safety_invalid")

    restore_plan = restore_plan_status if restore_plan_status in _VALID_RESTORE_PLAN else "unknown"
    restore_plan_satisfied = restore_plan == "valid"
    if not restore_plan_satisfied:
        missing.append("restore_plan_valid_required")
        blocked.append("restore_plan_invalid_or_missing")

    if not restore_supported:
        missing.append("restore_supported_required")
        blocked.append("restore_not_supported")
    if not restore_manual_only:
        missing.append("restore_manual_only_required")
        blocked.append("restore_must_be_manual_only")

    if rollback_strategy != "restore_snapshot_manual":
        missing.append("rollback_strategy_restore_snapshot_manual_required")
        blocked.append("rollback_strategy_invalid")
    if not rollback_metadata_present:
        missing.append("rollback_metadata_required")
        blocked.append("rollback_metadata_missing")

    if not txn_ref:
        missing.append("transaction_reference_required")
        blocked.append("transaction_reference_missing")
    if txn_ref and not transaction_rollback_metadata_valid:
        missing.append("transaction_rollback_metadata_valid_required")
        blocked.append("transaction_rollback_metadata_invalid")

    if not dry_ref:
        missing.append("dry_run_gate_reference_required")
        blocked.append("dry_run_gate_reference_missing")
    if not dry_run_gate_ready:
        missing.append("dry_run_gate_ready_required")
        blocked.append("dry_run_gate_not_ready")

    risk = (risk_level or "unknown").strip().lower()
    risk_requires_human_review = risk in {"high", "strict_gate"}
    if risk not in _KNOWN_RISK_LEVELS:
        missing.append("known_risk_level_required")
        blocked.append("unknown_risk_level")
    elif risk_requires_human_review:
        warnings.append("human_review_required_for_risk_level")

    if not manual_only:
        warnings.append("manual_only_forced_true")

    rollback_ready = len(blocked) == 0
    status = "rollback_ready_manual_only" if rollback_ready else ("manual_review_required" if risk_requires_human_review and risk in _KNOWN_RISK_LEVELS else "blocked")

    summary = {
        "workspace_id": workspace_id,
        "pool_id": pool_id,
        "item_id": item_id,
        "run_id": run_id,
        "action_id": action_id,
        "reason": reason,
        "risk_id": risk_id,
        "restore_plan_status": restore_plan,
    }

    return {
        "status": status,
        "rollback_ready": rollback_ready,
        "manual_only": True,
        "autonomous_execution_enabled": False,
        "automatic_rollback_enabled": False,
        "automatic_restore_enabled": False,
        "automatic_execute_enabled": False,
        "automatic_safe_apply_enabled": False,
        "automatic_verification_enabled": False,
        "restore_supported": bool(restore_supported),
        "restore_manual_only": True,
        "rollback_strategy": rollback_strategy,
        "requires_snapshot_manifest": True,
        "snapshot_reference_present": snapshot_ref,
        "snapshot_manifest_valid": bool(snapshot_manifest_valid),
        "snapshot_path_safety_valid": bool(snapshot_path_safety_valid),
        "requires_restore_plan": True,
        "restore_plan_satisfied": restore_plan_satisfied,
        "rollback_metadata_present": bool(rollback_metadata_present),
        "transaction_reference_present": txn_ref,
        "transaction_rollback_metadata_valid": bool(transaction_rollback_metadata_valid),
        "dry_run_gate_reference_present": dry_ref,
        "dry_run_gate_ready": bool(dry_run_gate_ready),
        "risk_level": risk,
        "risk_requires_human_review": risk_requires_human_review,
        "missing_requirements": sorted(set(missing)),
        "blocking_reasons": sorted(set(blocked)),
        "warnings": sorted(set(warnings)),
        "policy_notes": policy_notes,
        "summary": summary,
        "project_path": str(project_root),
        "risk_id": risk_id,
        "risk_manifest_path": risk_manifest_path,
        "transaction_id": transaction_id,
        "transaction_manifest_path": transaction_manifest_path,
        "snapshot_id": snapshot_id,
        "snapshot_manifest_path": snapshot_manifest_path,
        "restore_plan_status": restore_plan,
        "restore_plan_id": restore_plan_id,
        "dry_run_gate_id": dry_run_gate_id,
        "dry_run_gate_manifest_path": dry_run_gate_manifest_path,
        "allowlist_id": allowlist_id,
        "allowlist_manifest_path": allowlist_manifest_path,
    }


def create_rollback_readiness_record(*, data_root: str | Path, dry_run: bool = False, **kwargs: Any) -> dict[str, Any]:
    root = Path(data_root).expanduser().resolve()
    if "status" in kwargs and "rollback_ready" in kwargs:
        gate = dict(kwargs)
    else:
        gate = evaluate_rollback_readiness_gate(**kwargs)
    gid = f"rollback_gate_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    gdir = root / "atlas" / "rollback_readiness_gates" / gid
    manifest_path = gdir / "manifest.json"
    _ensure_under(root, manifest_path, "manifest_outside_data_root")
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "rollback_gate_id": gid,
        "created_at": _utc_now(),
        "project_path": gate["project_path"],
        "data_root": str(root),
        "workspace_id": gate["summary"].get("workspace_id", ""),
        "pool_id": gate["summary"].get("pool_id", ""),
        "item_id": gate["summary"].get("item_id", ""),
        "run_id": gate["summary"].get("run_id", ""),
        "action_id": gate["summary"].get("action_id", ""),
        "reason": gate["summary"].get("reason", ""),
        "risk_id": gate.get("risk_id", ""),
        "risk_level": gate["risk_level"],
        "risk_manifest_path": gate.get("risk_manifest_path", ""),
        "transaction_id": gate.get("transaction_id", ""),
        "transaction_manifest_path": gate.get("transaction_manifest_path", ""),
        "snapshot_id": gate.get("snapshot_id", ""),
        "snapshot_manifest_path": gate.get("snapshot_manifest_path", ""),
        "restore_plan_status": gate.get("restore_plan_status", "unknown"),
        "restore_plan_id": gate.get("restore_plan_id", ""),
        "restore_supported": gate["restore_supported"],
        "restore_manual_only": gate["restore_manual_only"],
        "rollback_metadata_present": gate["rollback_metadata_present"],
        "rollback_strategy": gate["rollback_strategy"],
        "snapshot_manifest_valid": gate["snapshot_manifest_valid"],
        "snapshot_path_safety_valid": gate["snapshot_path_safety_valid"],
        "transaction_rollback_metadata_valid": gate["transaction_rollback_metadata_valid"],
        "dry_run_gate_id": gate.get("dry_run_gate_id", ""),
        "dry_run_gate_manifest_path": gate.get("dry_run_gate_manifest_path", ""),
        "dry_run_gate_ready": gate["dry_run_gate_ready"],
        "allowlist_id": gate.get("allowlist_id", ""),
        "allowlist_manifest_path": gate.get("allowlist_manifest_path", ""),
        "rollback_ready": gate["rollback_ready"],
        "status": gate["status"],
        "missing_requirements": gate["missing_requirements"],
        "blocking_reasons": gate["blocking_reasons"],
        "warnings": gate["warnings"],
        "policy_notes": gate["policy_notes"],
        "summary": gate["summary"],
        "manual_only": True,
        "autonomous_execution_enabled": False,
        "automatic_rollback_enabled": False,
        "automatic_restore_enabled": False,
        "automatic_execute_enabled": False,
        "automatic_safe_apply_enabled": False,
        "automatic_verification_enabled": False,
    }
    if not dry_run:
        gdir.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"status": "planned" if dry_run else "created", "rollback_gate_id": gid, "gate_dir": str(gdir), "manifest_path": str(manifest_path), "manifest": manifest, "dry_run": dry_run}


def read_rollback_readiness_record(*, manifest_path: str | Path | None = None, rollback_gate_id: str = "", data_root: str | Path | None = None) -> dict[str, Any]:
    manifest = Path(manifest_path).resolve() if manifest_path else Path(data_root).resolve() / "atlas" / "rollback_readiness_gates" / rollback_gate_id / "manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported_schema_version")
    root = Path(data_root if data_root is not None else payload.get("data_root", "")).resolve()
    _ensure_under(root, manifest, "manifest_outside_data_root")
    return {"manifest": payload, "warnings": []}


def summarize_rollback_readiness_record(*, manifest_path: str | Path | None = None, rollback_gate_id: str = "", data_root: str | Path | None = None) -> dict[str, Any]:
    m = read_rollback_readiness_record(manifest_path=manifest_path, rollback_gate_id=rollback_gate_id, data_root=data_root)["manifest"]
    return {
        "rollback_gate_id": m.get("rollback_gate_id", ""),
        "status": m.get("status", "unknown"),
        "rollback_ready": bool(m.get("rollback_ready", False)),
        "manual_only": True,
        "blocking_reasons": list(m.get("blocking_reasons", [])),
        "missing_requirements": list(m.get("missing_requirements", [])),
        "warnings": list(m.get("warnings", [])),
        "summary": dict(m.get("summary", {})),
    }
