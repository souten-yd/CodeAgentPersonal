from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "atlas.dry_run_approval_gate.v1"

_VALID_DRY_RUN = {"missing", "planned", "passed", "failed", "unknown"}
_VALID_APPROVAL = {"missing", "pending", "approved", "rejected", "unknown"}
_VALID_DECISION = {"approve", "reject", "pending", "unknown"}
_APPROVAL_RISKS = {"medium", "high", "strict_gate"}
_KNOWN_RISKS = {"low", "medium", "high", "strict_gate"}
_REQUIRED_TEXT = "EXECUTE ONE ACTION"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_under(root: Path, target: Path, code: str) -> Path:
    rr = root.resolve()
    tt = target.resolve()
    if os.path.commonpath([str(rr), str(tt)]) != str(rr):
        raise ValueError(code)
    return tt


def evaluate_dry_run_approval_gate(
    *,
    project_path: str | Path,
    workspace_id: str = "",
    pool_id: str = "",
    item_id: str = "",
    run_id: str = "",
    action_id: str = "",
    action_kind: str = "",
    reason: str = "",
    risk_level: str = "unknown",
    risk_id: str = "",
    risk_manifest_path: str = "",
    transaction_id: str = "",
    transaction_manifest_path: str = "",
    snapshot_id: str = "",
    snapshot_manifest_path: str = "",
    allowlist_id: str = "",
    allowlist_manifest_path: str = "",
    dry_run_status: str = "missing",
    dry_run_result_id: str = "",
    approval_status: str = "missing",
    confirmation_text: str = "",
    confirmation_token_present: bool = False,
    explicit_decision: str = "unknown",
    payload_valid: bool = False,
    manual_only: bool = True,
) -> dict[str, Any]:
    project_root = Path(project_path).expanduser().resolve()
    missing_requirements: list[str] = []
    blocking_reasons: list[str] = []
    warnings: list[str] = []
    policy_notes = [
        "metadata_only_gate",
        "gate_readiness_does_not_execute",
        "dry_run_not_auto_executed",
        "approval_not_auto_granted",
    ]

    dry_run_norm = dry_run_status if dry_run_status in _VALID_DRY_RUN else "unknown"
    if dry_run_norm == "unknown" and dry_run_status not in _VALID_DRY_RUN:
        warnings.append("dry_run_status_unrecognized")
    approval_norm = approval_status if approval_status in _VALID_APPROVAL else "unknown"
    if approval_norm == "unknown" and approval_status not in _VALID_APPROVAL:
        warnings.append("approval_status_unrecognized")
    decision_norm = explicit_decision if explicit_decision in _VALID_DECISION else "unknown"
    if decision_norm == "unknown" and explicit_decision not in _VALID_DECISION:
        warnings.append("explicit_decision_unrecognized")

    risk = (risk_level or "unknown").strip().lower()
    risk_gate_satisfied = risk in _KNOWN_RISKS
    if not risk_gate_satisfied:
        missing_requirements.append("risk_level")
        blocking_reasons.append("unknown_risk_blocked")

    requires_explicit_approval = risk in _APPROVAL_RISKS
    explicit_approval_satisfied = not requires_explicit_approval or (approval_norm == "approved" and decision_norm == "approve")
    if requires_explicit_approval and not explicit_approval_satisfied:
        missing_requirements.append("explicit_approval")
        blocking_reasons.append("explicit_approval_required")

    dry_run_satisfied = dry_run_norm == "passed"
    if not dry_run_satisfied:
        missing_requirements.append("dry_run_passed")
        blocking_reasons.append("dry_run_failed_blocked" if dry_run_norm == "failed" else "dry_run_missing_or_not_passed")

    confirmation_token_satisfied = bool(confirmation_token_present)
    if not confirmation_token_satisfied:
        missing_requirements.append("confirmation_token")
        blocking_reasons.append("confirmation_token_missing")

    confirmation_text_satisfied = confirmation_text == _REQUIRED_TEXT
    if not confirmation_text_satisfied:
        missing_requirements.append("confirmation_text")
        blocking_reasons.append("confirmation_text_mismatch")

    payload_ok = bool(payload_valid)
    if not payload_ok:
        missing_requirements.append("payload_valid")
        blocking_reasons.append("payload_invalid")

    transaction_reference_present = bool(transaction_id or transaction_manifest_path)
    snapshot_reference_present = bool(snapshot_id or snapshot_manifest_path)
    allowlist_reference_present = bool(allowlist_id or allowlist_manifest_path)

    if not transaction_reference_present:
        missing_requirements.append("transaction_reference")
        blocking_reasons.append("transaction_reference_required")
    if not snapshot_reference_present:
        missing_requirements.append("snapshot_reference")
        blocking_reasons.append("snapshot_reference_required")
    if not allowlist_reference_present:
        warnings.append("allowlist_reference_missing")

    manual_boundary = True if manual_only else True
    if manual_only is False:
        warnings.append("manual_only_forced_true")

    gate_ready = all([
        dry_run_satisfied,
        confirmation_token_satisfied,
        confirmation_text_satisfied,
        payload_ok,
        risk_gate_satisfied,
        explicit_approval_satisfied,
        transaction_reference_present,
        snapshot_reference_present,
    ])

    if gate_ready:
        status = "ready_for_manual_execute"
    elif blocking_reasons:
        status = "blocked"
    elif warnings:
        status = "manual_review_required"
    else:
        status = "unknown"

    summary = {
        "workspace_id": workspace_id,
        "pool_id": pool_id,
        "item_id": item_id,
        "run_id": run_id,
        "action_id": action_id,
        "action_kind": action_kind,
        "reason": reason,
        "risk_level": risk,
        "dry_run_status": dry_run_norm,
        "approval_status": approval_norm,
    }

    return {
        "status": status,
        "gate_ready": gate_ready,
        "manual_only": manual_boundary,
        "autonomous_execution_enabled": False,
        "automatic_execute_enabled": False,
        "automatic_dry_run_enabled": False,
        "automatic_approval_enabled": False,
        "automatic_verification_enabled": False,
        "automatic_safe_apply_enabled": False,
        "automatic_rollback_enabled": False,
        "requires_dry_run": True,
        "dry_run_satisfied": dry_run_satisfied,
        "requires_confirmation_token": True,
        "confirmation_token_satisfied": confirmation_token_satisfied,
        "requires_confirmation_text": _REQUIRED_TEXT,
        "confirmation_text_satisfied": confirmation_text_satisfied,
        "requires_explicit_approval": requires_explicit_approval,
        "explicit_approval_satisfied": explicit_approval_satisfied,
        "risk_level": risk,
        "risk_gate_satisfied": risk_gate_satisfied,
        "transaction_reference_present": transaction_reference_present,
        "snapshot_reference_present": snapshot_reference_present,
        "allowlist_reference_present": allowlist_reference_present,
        "payload_valid": payload_ok,
        "missing_requirements": sorted(set(missing_requirements)),
        "blocking_reasons": sorted(set(blocking_reasons)),
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
        "allowlist_id": allowlist_id,
        "allowlist_manifest_path": allowlist_manifest_path,
        "dry_run_status": dry_run_norm,
        "dry_run_result_id": dry_run_result_id,
        "approval_status": approval_norm,
        "confirmation_token_present": confirmation_token_satisfied,
        "explicit_decision": decision_norm,
    }


def create_dry_run_approval_record(*, data_root: str | Path, dry_run: bool = False, **kwargs: Any) -> dict[str, Any]:
    root = Path(data_root).expanduser().resolve()
    gate = evaluate_dry_run_approval_gate(**kwargs)
    gate_id = f"gate_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    gate_dir = root / "atlas" / "dry_run_approval_gates" / gate_id
    manifest_path = gate_dir / "manifest.json"
    _ensure_under(root, manifest_path, "manifest_outside_data_root")

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "gate_id": gate_id,
        "created_at": _utc_now(),
        "project_path": gate["project_path"],
        "data_root": str(root),
        "workspace_id": gate["summary"].get("workspace_id", ""),
        "pool_id": gate["summary"].get("pool_id", ""),
        "item_id": gate["summary"].get("item_id", ""),
        "run_id": gate["summary"].get("run_id", ""),
        "action_id": gate["summary"].get("action_id", ""),
        "action_kind": gate["summary"].get("action_kind", ""),
        "reason": gate["summary"].get("reason", ""),
        "risk_id": gate.get("risk_id", ""),
        "risk_level": gate["risk_level"],
        "risk_manifest_path": gate.get("risk_manifest_path", ""),
        "transaction_id": gate.get("transaction_id", ""),
        "transaction_manifest_path": gate.get("transaction_manifest_path", ""),
        "snapshot_id": gate.get("snapshot_id", ""),
        "snapshot_manifest_path": gate.get("snapshot_manifest_path", ""),
        "allowlist_id": gate.get("allowlist_id", ""),
        "allowlist_manifest_path": gate.get("allowlist_manifest_path", ""),
        "dry_run_status": gate["dry_run_status"],
        "dry_run_result_id": gate.get("dry_run_result_id", ""),
        "approval_status": gate["approval_status"],
        "confirmation_token_present": gate["confirmation_token_present"],
        "confirmation_text_required": _REQUIRED_TEXT,
        "confirmation_text_satisfied": gate["confirmation_text_satisfied"],
        "explicit_decision": gate.get("explicit_decision", "unknown"),
        "payload_valid": gate["payload_valid"],
        "gate_ready": gate["gate_ready"],
        "status": gate["status"],
        "missing_requirements": gate["missing_requirements"],
        "blocking_reasons": gate["blocking_reasons"],
        "warnings": gate["warnings"],
        "policy_notes": gate["policy_notes"],
        "summary": gate["summary"],
        "manual_only": True,
        "autonomous_execution_enabled": False,
        "automatic_execute_enabled": False,
        "automatic_dry_run_enabled": False,
        "automatic_approval_enabled": False,
        "automatic_verification_enabled": False,
        "automatic_safe_apply_enabled": False,
        "automatic_rollback_enabled": False,
    }

    if not dry_run:
        gate_dir.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return {
        "status": "planned" if dry_run else "created",
        "gate_id": gate_id,
        "gate_dir": str(gate_dir),
        "manifest_path": str(manifest_path),
        "manifest": manifest,
        "dry_run": dry_run,
    }


def read_dry_run_approval_record(*, manifest_path: str | Path | None = None, gate_id: str = "", data_root: str | Path | None = None) -> dict[str, Any]:
    manifest = Path(manifest_path).resolve() if manifest_path else Path(data_root).resolve() / "atlas" / "dry_run_approval_gates" / gate_id / "manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported_schema_version")
    root = Path(data_root if data_root is not None else payload.get("data_root", "")).resolve()
    _ensure_under(root, manifest, "manifest_outside_data_root")
    return {"manifest": payload, "warnings": []}


def summarize_dry_run_approval_record(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": manifest.get("status", "unknown"),
        "gate_ready": bool(manifest.get("gate_ready")),
        "missing_count": len(manifest.get("missing_requirements", [])),
        "blocking_count": len(manifest.get("blocking_reasons", [])),
        "warning_count": len(manifest.get("warnings", [])),
    }
