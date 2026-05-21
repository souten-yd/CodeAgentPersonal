from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "atlas.artifact_capture_gate.v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_under(root: Path, target: Path, code: str) -> Path:
    rr = root.resolve()
    tt = target.resolve()
    if os.path.commonpath([str(rr), str(tt)]) != str(rr):
        raise ValueError(code)
    return tt


def _safe_optional_manifest_path(path_value: str | None, *, data_root: Path, project_root: Path, allow_project_path: bool = False) -> tuple[str, bool, str | None]:
    if not path_value:
        return "", False, None
    raw = Path(path_value).expanduser()
    if not raw.is_absolute():
        cand = (data_root / raw).resolve()
    else:
        cand = raw.resolve()

    data_ok = os.path.commonpath([str(data_root), str(cand)]) == str(data_root)
    project_ok = allow_project_path and os.path.commonpath([str(project_root), str(cand)]) == str(project_root)
    if not (data_ok or project_ok):
        return str(cand), False, "reference_path_outside_allowed_roots"
    return str(cand), cand.exists(), None


def _is_reference_present(id_value: str | None, path_present: bool) -> bool:
    return bool((id_value or "").strip()) or bool(path_present)


def evaluate_artifact_capture_gate(*, project_path: str | Path, workspace_id: str = "", pool_id: str = "", item_id: str = "", run_id: str = "", action_id: str = "", reason: str = "", plan_id: str = "", plan_summary: str = "", plan_manifest_path: str = "", snapshot_id: str = "", snapshot_manifest_path: str = "", transaction_id: str = "", transaction_manifest_path: str = "", rollback_metadata_present: bool = False, rollback_readiness_gate_id: str = "", rollback_readiness_manifest_path: str = "", risk_id: str = "", risk_manifest_path: str = "", allowlist_id: str = "", allowlist_manifest_path: str = "", dry_run_gate_id: str = "", dry_run_gate_manifest_path: str = "", dry_run_result_id: str = "", dry_run_result_path: str = "", execution_result_id: str = "", execution_result_path: str = "", verification_plan_id: str = "", verification_plan_path: str = "", verification_result_id: str = "", verification_result_path: str = "", warnings: list[str] | None = None, recovery_instructions: list[str] | None = None, artifact_notes: list[str] | None = None, manual_only: bool = True, data_root: str | Path | None = None) -> dict[str, Any]:
    project_root = Path(project_path).expanduser().resolve()
    root = Path(data_root).expanduser().resolve() if data_root is not None else project_root

    eval_warnings = list(warnings or [])
    blocking_reasons: list[str] = []
    policy_notes = [
        "metadata_only_gate",
        "does_not_execute_actions",
        "does_not_run_dry_run",
        "does_not_approve",
        "does_not_verify",
        "does_not_apply_patches",
        "does_not_restore",
        "does_not_fabricate_results",
    ]

    refs = {
        "plan_manifest_path": _safe_optional_manifest_path(plan_manifest_path, data_root=root, project_root=project_root, allow_project_path=True),
        "snapshot_manifest_path": _safe_optional_manifest_path(snapshot_manifest_path, data_root=root, project_root=project_root),
        "transaction_manifest_path": _safe_optional_manifest_path(transaction_manifest_path, data_root=root, project_root=project_root),
        "rollback_readiness_manifest_path": _safe_optional_manifest_path(rollback_readiness_manifest_path, data_root=root, project_root=project_root),
        "risk_manifest_path": _safe_optional_manifest_path(risk_manifest_path, data_root=root, project_root=project_root),
        "allowlist_manifest_path": _safe_optional_manifest_path(allowlist_manifest_path, data_root=root, project_root=project_root),
        "dry_run_gate_manifest_path": _safe_optional_manifest_path(dry_run_gate_manifest_path, data_root=root, project_root=project_root),
        "dry_run_result_path": _safe_optional_manifest_path(dry_run_result_path, data_root=root, project_root=project_root, allow_project_path=True),
        "execution_result_path": _safe_optional_manifest_path(execution_result_path, data_root=root, project_root=project_root, allow_project_path=True),
        "verification_plan_path": _safe_optional_manifest_path(verification_plan_path, data_root=root, project_root=project_root, allow_project_path=True),
        "verification_result_path": _safe_optional_manifest_path(verification_result_path, data_root=root, project_root=project_root, allow_project_path=True),
    }
    for k, (_, _, err) in refs.items():
        if err:
            eval_warnings.append(f"{k}:{err}")
            blocking_reasons.append(f"{k}_invalid")

    plan_present = bool(plan_summary.strip() or plan_id.strip()) or _is_reference_present(plan_id, refs["plan_manifest_path"][1])
    snapshot_present = _is_reference_present(snapshot_id, refs["snapshot_manifest_path"][1])
    transaction_present = _is_reference_present(transaction_id, refs["transaction_manifest_path"][1])
    rollback_readiness_present = _is_reference_present(rollback_readiness_gate_id, refs["rollback_readiness_manifest_path"][1])
    risk_present = _is_reference_present(risk_id, refs["risk_manifest_path"][1])
    allowlist_present = _is_reference_present(allowlist_id, refs["allowlist_manifest_path"][1])
    dry_gate_present = _is_reference_present(dry_run_gate_id, refs["dry_run_gate_manifest_path"][1])

    dry_result_present = _is_reference_present(dry_run_result_id, refs["dry_run_result_path"][1])
    execution_result_present = _is_reference_present(execution_result_id, refs["execution_result_path"][1])
    verification_plan_present = _is_reference_present(verification_plan_id, refs["verification_plan_path"][1])
    verification_result_present = _is_reference_present(verification_result_id, refs["verification_result_path"][1])

    warnings_present = warnings is not None
    recovery_present = bool(recovery_instructions)

    required_artifacts = [
        "plan_reference", "snapshot_reference", "transaction_reference", "rollback_metadata", "rollback_readiness_reference",
        "risk_reference", "allowlist_reference", "dry_run_gate_reference", "warnings_list", "recovery_instructions",
    ]
    optional_artifacts = ["dry_run_result_reference", "execution_result_reference", "verification_plan_reference", "verification_result_reference"]

    checks = {
        "plan_reference": plan_present,
        "snapshot_reference": snapshot_present,
        "transaction_reference": transaction_present,
        "rollback_metadata": bool(rollback_metadata_present),
        "rollback_readiness_reference": rollback_readiness_present,
        "risk_reference": risk_present,
        "allowlist_reference": allowlist_present,
        "dry_run_gate_reference": dry_gate_present,
        "warnings_list": warnings_present,
        "recovery_instructions": recovery_present,
        "dry_run_result_reference": dry_result_present,
        "execution_result_reference": execution_result_present,
        "verification_plan_reference": verification_plan_present,
        "verification_result_reference": verification_result_present,
    }

    missing_required = [k for k in required_artifacts if not checks[k]]
    missing_optional = [k for k in optional_artifacts if not checks[k]]
    blocking_reasons.extend([f"{x}_missing" for x in missing_required])

    artifact_capture_ready = not missing_required and not any("_invalid" in x for x in blocking_reasons)
    status = "artifact_capture_ready_manual_only" if artifact_capture_ready else "blocked"

    artifact_index = {
        "plan_manifest_path": refs["plan_manifest_path"][0],
        "snapshot_manifest_path": refs["snapshot_manifest_path"][0],
        "transaction_manifest_path": refs["transaction_manifest_path"][0],
        "rollback_readiness_manifest_path": refs["rollback_readiness_manifest_path"][0],
        "risk_manifest_path": refs["risk_manifest_path"][0],
        "allowlist_manifest_path": refs["allowlist_manifest_path"][0],
        "dry_run_gate_manifest_path": refs["dry_run_gate_manifest_path"][0],
        "dry_run_result_path": refs["dry_run_result_path"][0],
        "execution_result_path": refs["execution_result_path"][0],
        "verification_plan_path": refs["verification_plan_path"][0],
        "verification_result_path": refs["verification_result_path"][0],
        "data_root": str(root),
    }

    return {
        "status": status,
        "artifact_capture_ready": artifact_capture_ready,
        "manual_only": True,
        "autonomous_execution_enabled": False,
        "automatic_artifact_capture_enabled": False,
        "automatic_execute_enabled": False,
        "automatic_dry_run_enabled": False,
        "automatic_approval_enabled": False,
        "automatic_verification_enabled": False,
        "automatic_command_execution_enabled": False,
        "automatic_safe_apply_enabled": False,
        "automatic_rollback_enabled": False,
        "automatic_restore_enabled": False,
        "plan_reference_present": plan_present,
        "snapshot_reference_present": snapshot_present,
        "transaction_reference_present": transaction_present,
        "rollback_metadata_present": bool(rollback_metadata_present),
        "rollback_readiness_reference_present": rollback_readiness_present,
        "risk_reference_present": risk_present,
        "allowlist_reference_present": allowlist_present,
        "dry_run_gate_reference_present": dry_gate_present,
        "dry_run_result_reference_present": dry_result_present,
        "execution_result_reference_present": execution_result_present,
        "verification_plan_reference_present": verification_plan_present,
        "verification_result_reference_present": verification_result_present,
        "warnings_present": warnings_present,
        "recovery_instructions_present": recovery_present,
        "required_artifacts": required_artifacts,
        "optional_artifacts": optional_artifacts,
        "missing_required_artifacts": sorted(set(missing_required)),
        "missing_optional_artifacts": sorted(set(missing_optional)),
        "blocking_reasons": sorted(set(blocking_reasons)),
        "warnings": sorted(set(eval_warnings)),
        "policy_notes": policy_notes,
        "artifact_index": artifact_index,
        "summary": {
            "workspace_id": workspace_id, "pool_id": pool_id, "item_id": item_id, "run_id": run_id, "action_id": action_id,
            "reason": reason, "manual_only": bool(manual_only), "artifact_notes": list(artifact_notes or []),
        },
        "project_path": str(project_root),
    }


def create_artifact_capture_record(*, data_root: str | Path, dry_run: bool = False, **kwargs: Any) -> dict[str, Any]:
    root = Path(data_root).expanduser().resolve()
    gate = kwargs if "artifact_capture_ready" in kwargs else evaluate_artifact_capture_gate(data_root=root, **kwargs)
    gid = f"artifact_gate_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    gdir = root / "atlas" / "artifact_capture_gates" / gid
    manifest_path = gdir / "manifest.json"
    _ensure_under(root, manifest_path, "manifest_outside_data_root")

    manifest = {"schema_version": SCHEMA_VERSION, "artifact_gate_id": gid, "created_at": _utc_now(), "data_root": str(root), **gate}
    if not dry_run:
        gdir.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"status": "planned" if dry_run else "created", "artifact_gate_id": gid, "gate_dir": str(gdir), "manifest_path": str(manifest_path), "manifest": manifest, "dry_run": dry_run}


def read_artifact_capture_record(*, manifest_path: str | Path | None = None, artifact_gate_id: str = "", data_root: str | Path | None = None) -> dict[str, Any]:
    manifest = Path(manifest_path).resolve() if manifest_path else Path(data_root).resolve() / "atlas" / "artifact_capture_gates" / artifact_gate_id / "manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported_schema_version")
    root = Path(data_root if data_root is not None else payload.get("data_root", "")).resolve()
    _ensure_under(root, manifest, "manifest_outside_data_root")
    return {"manifest": payload, "warnings": []}


def summarize_artifact_capture_record(*, manifest_path: str | Path | None = None, artifact_gate_id: str = "", data_root: str | Path | None = None) -> dict[str, Any]:
    m = read_artifact_capture_record(manifest_path=manifest_path, artifact_gate_id=artifact_gate_id, data_root=data_root)["manifest"]
    return {
        "artifact_gate_id": m.get("artifact_gate_id", ""),
        "status": m.get("status", "unknown"),
        "artifact_capture_ready": bool(m.get("artifact_capture_ready", False)),
        "manual_only": True,
        "missing_required_artifacts": list(m.get("missing_required_artifacts", [])),
        "missing_optional_artifacts": list(m.get("missing_optional_artifacts", [])),
        "blocking_reasons": list(m.get("blocking_reasons", [])),
    }
