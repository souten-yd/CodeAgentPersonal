from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.atlas.level1_execution_artifact_capture import (
    validate_level1_execution_artifact_manifest,
)
from app.atlas.stop_kill_switch_gate import evaluate_stop_kill_switch_gate

SCHEMA_VERSION = "atlas.level1_stop_kill_switch_runtime.v1"
RUNTIME_LEVEL = "level_0_manual_only"


def create_level1_stop_kill_switch_runtime_manifest(
    *,
    project_path: str | Path,
    data_root: str | Path | None = None,
    workspace_id: str = "default",
    pool_id: str = "",
    item_id: str = "",
    run_id: str = "",
    action_id: str = "",
    execution_artifact_manifest: dict[str, Any] | None = None,
    execution_artifact_manifest_path: str = "",
    stop_gate_manifest: dict[str, Any] | None = None,
    stop_gate_manifest_path: str = "",
    stop_requested: bool = False,
    stop_acknowledged: bool = False,
    stop_request_id: str = "",
    recovery_instructions: list[str] | None = None,
    warnings: list[str] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    created = created_at or _utc_now()
    project_root = Path(project_path).expanduser().resolve()
    root = Path(data_root).expanduser().resolve() if data_root is not None else project_root
    execution_artifact = dict(execution_artifact_manifest or {})
    execution_artifact_valid = False
    execution_artifact_id = _safe_text(execution_artifact.get("artifact_id"))
    execution_artifact_status = _safe_text(execution_artifact.get("status"), "missing")
    execution_artifact_errors: list[str] = []
    if execution_artifact:
        try:
            validate_level1_execution_artifact_manifest(execution_artifact)
            execution_artifact_valid = True
        except ValueError as exc:
            execution_artifact_errors.append(str(exc))

    gate = dict(
        stop_gate_manifest
        or evaluate_stop_kill_switch_gate(
            project_path=project_root,
            data_root=root,
            workspace_id=workspace_id,
            pool_id=pool_id,
            item_id=item_id,
            run_id=run_id,
            action_id=action_id,
            stop_requested=stop_requested,
            stop_acknowledged=stop_acknowledged,
            stop_request_id=stop_request_id,
            kill_switch_available=True,
            stop_state_visible=True,
            ui_stop_visible=True,
            cli_stop_available=True,
            api_stop_available=True,
            operator_loop_stop_visible=True,
            artifact_gate_id=execution_artifact_id,
            artifact_capture_manifest_path=execution_artifact_manifest_path,
            recovery_instructions=recovery_instructions or ["Manual operator halt and recovery remains required."],
            warnings=warnings or [],
            policy_notes=["scale_123_stop_kill_switch_runtime_integration"],
        )
    )
    gate_ready = bool(gate.get("stop_gate_ready"))
    stop_is_active = bool(gate.get("stop_requested") or gate.get("stop_acknowledged") or stop_requested or stop_acknowledged)
    continuation_blocked = stop_is_active or not gate_ready or not execution_artifact_valid
    blocking_reasons = list(gate.get("blocking_reasons") or [])
    if not execution_artifact_valid:
        blocking_reasons.append("execution_artifact_manifest_invalid_or_missing")
    if stop_is_active:
        blocking_reasons.append("stop_state_blocks_continuation")

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "runtime_integration_id": _integration_id(run_id=run_id, action_id=action_id, created_at=created),
        "created_at": created,
        "workspace_id": _safe_text(workspace_id, "default"),
        "pool_id": _safe_text(pool_id),
        "item_id": _safe_text(item_id),
        "run_id": _safe_text(run_id, "run"),
        "action_id": _safe_text(action_id, "action"),
        "project_path": str(project_root),
        "data_root": str(root),
        "runtime_level": RUNTIME_LEVEL,
        "manual_only": True,
        "runtime_integration_ready": gate_ready and execution_artifact_valid,
        "stop_gate_ready": gate_ready,
        "stop_requested": bool(gate.get("stop_requested") or stop_requested),
        "stop_acknowledged": bool(gate.get("stop_acknowledged") or stop_acknowledged),
        "stop_request_id": _safe_text(gate.get("stop_request_id") or stop_request_id),
        "stop_gate_manifest_path": _safe_text(stop_gate_manifest_path),
        "execution_artifact_id": execution_artifact_id,
        "execution_artifact_status": execution_artifact_status,
        "execution_artifact_manifest_path": _safe_text(execution_artifact_manifest_path),
        "execution_artifact_valid": execution_artifact_valid,
        "continuation_blocked": continuation_blocked,
        "continuation_after_stop_allowed": False,
        "auto_continue_enabled": False,
        "execute_all_enabled": False,
        "execution_enabled": False,
        "level1_execution_enabled": False,
        "autonomous_execution_enabled": False,
        "execution_performed": False,
        "mutation_performed": False,
        "verification_performed": False,
        "rollback_performed": False,
        "retry_performed": False,
        "process_kill_performed": False,
        "backend_authoritative": True,
        "vue_authoritative": False,
        "blocking_reasons": sorted(set(blocking_reasons)),
        "missing_required_evidence": sorted(set(gate.get("missing_required_evidence") or [])),
        "execution_artifact_errors": execution_artifact_errors,
        "stop_gate_summary": {
            "status": _safe_text(gate.get("status"), "unknown"),
            "missing_stop_controls": list(gate.get("missing_stop_controls") or []),
            "stop_state_summary": dict(gate.get("stop_state_summary") or {}),
        },
        "warnings": [
            "SCALE-123 integrates stop / kill-switch metadata only.",
            "Stop state blocks continuation, but this module does not kill processes or stop real jobs.",
            *_safe_list(warnings),
        ],
        "policy_notes": [
            "scale_123_stop_kill_switch_runtime_integration",
            "metadata_only",
            "no_auto_continue_after_stop",
            "no_process_kill",
            "no_execution_enablement",
        ],
        "next_required_pr": "PR-ATLAS-SCALE-124",
    }
    return validate_level1_stop_kill_switch_runtime_manifest(manifest)


def validate_level1_stop_kill_switch_runtime_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    required = [
        "schema_version",
        "runtime_integration_id",
        "runtime_level",
        "manual_only",
        "runtime_integration_ready",
        "stop_gate_ready",
        "execution_artifact_valid",
        "continuation_blocked",
        "continuation_after_stop_allowed",
        "auto_continue_enabled",
        "execute_all_enabled",
        "execution_enabled",
        "level1_execution_enabled",
        "autonomous_execution_enabled",
        "execution_performed",
        "mutation_performed",
        "process_kill_performed",
        "backend_authoritative",
        "vue_authoritative",
    ]
    missing = [field for field in required if field not in manifest]
    if missing:
        raise ValueError(f"missing_required_fields:{','.join(missing)}")
    invariants = {
        "schema_version": manifest.get("schema_version") == SCHEMA_VERSION,
        "runtime_level": manifest.get("runtime_level") == RUNTIME_LEVEL,
        "manual_only": manifest.get("manual_only") is True,
        "continuation_after_stop_allowed": manifest.get("continuation_after_stop_allowed") is False,
        "auto_continue_enabled": manifest.get("auto_continue_enabled") is False,
        "execute_all_enabled": manifest.get("execute_all_enabled") is False,
        "execution_enabled": manifest.get("execution_enabled") is False,
        "level1_execution_enabled": manifest.get("level1_execution_enabled") is False,
        "autonomous_execution_enabled": manifest.get("autonomous_execution_enabled") is False,
        "execution_performed": manifest.get("execution_performed") is False,
        "mutation_performed": manifest.get("mutation_performed") is False,
        "verification_performed": manifest.get("verification_performed") is False,
        "rollback_performed": manifest.get("rollback_performed") is False,
        "retry_performed": manifest.get("retry_performed") is False,
        "process_kill_performed": manifest.get("process_kill_performed") is False,
        "backend_authoritative": manifest.get("backend_authoritative") is True,
        "vue_authoritative": manifest.get("vue_authoritative") is False,
    }
    violations = [key for key, ok in invariants.items() if not ok]
    if violations:
        raise ValueError(f"invariant_violation:{','.join(sorted(violations))}")
    if manifest.get("stop_requested") and manifest.get("continuation_blocked") is not True:
        raise ValueError("invariant_violation:stop_requested_must_block_continuation")
    if manifest.get("stop_acknowledged") and manifest.get("continuation_blocked") is not True:
        raise ValueError("invariant_violation:stop_acknowledged_must_block_continuation")
    return manifest


def write_level1_stop_kill_switch_runtime_manifest(*, data_root: str | Path, manifest: dict[str, Any]) -> Path:
    validated = validate_level1_stop_kill_switch_runtime_manifest(manifest)
    root = Path(data_root).expanduser().resolve()
    integration_id = str(validated["runtime_integration_id"])
    manifest_path = root / "atlas" / "level1_stop_kill_switch_runtime" / integration_id / "manifest.json"
    _ensure_under(root, manifest_path, "manifest_outside_data_root")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(validated, indent=2, sort_keys=True), encoding="utf-8")
    return manifest_path


def load_level1_stop_kill_switch_runtime_manifest(*, manifest_path: str | Path, data_root: str | Path | None = None) -> dict[str, Any]:
    path = Path(manifest_path).expanduser().resolve()
    if data_root is not None:
        _ensure_under(Path(data_root).expanduser().resolve(), path, "manifest_outside_data_root")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return validate_level1_stop_kill_switch_runtime_manifest(payload)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _integration_id(*, run_id: str, action_id: str, created_at: str) -> str:
    created_norm = created_at.replace(":", "").replace("-", "").replace("+", "").replace(".", "")
    return f"stop_runtime_{_safe_text(run_id, 'run')}_{_safe_text(action_id, 'action')}_{created_norm}_{uuid.uuid4().hex[:8]}"


def _safe_text(value: Any, fallback: str = "") -> str:
    if isinstance(value, str):
        text = value.strip()
        if text:
            return text[:512]
    return fallback


def _safe_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip()[:512] for item in value if isinstance(item, str) and item.strip()]


def _ensure_under(root: Path, target: Path, code: str) -> Path:
    rr = root.resolve()
    tt = target.resolve()
    if os.path.commonpath([str(rr), str(tt)]) != str(rr):
        raise ValueError(code)
    return tt
