from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "atlas.level1_execution_artifact.v1"
RUNTIME_LEVEL = "level_0_manual_only"


def create_level1_execution_artifact_manifest(
    *,
    workspace_id: str = "default",
    pool_id: str = "",
    item_id: str = "",
    run_id: str = "",
    action_id: str = "",
    command_summary: str = "",
    runner_id: str = "",
    runner_manifest_path: str = "",
    approval_token_id: str = "",
    dry_run_artifact_id: str = "",
    dry_run_manifest_path: str = "",
    allowlist_id: str = "",
    allowlist_manifest_path: str = "",
    risk_level: str = "unknown",
    status: str = "not_executed",
    warnings: list[str] | None = None,
    policy_notes: list[str] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    created = created_at or _utc_now()
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "artifact_id": _artifact_id(run_id=run_id, action_id=action_id, created_at=created),
        "created_at": created,
        "workspace_id": _safe_text(workspace_id, "default"),
        "pool_id": _safe_text(pool_id),
        "item_id": _safe_text(item_id),
        "run_id": _safe_text(run_id, "run"),
        "action_id": _safe_text(action_id, "action"),
        "command_summary": _safe_text(command_summary, "Execution artifact metadata only; no command was executed by this capture."),
        "runner_id": _safe_text(runner_id),
        "runner_manifest_path": _safe_text(runner_manifest_path),
        "approval_token_id": _safe_text(approval_token_id),
        "dry_run_artifact_id": _safe_text(dry_run_artifact_id),
        "dry_run_manifest_path": _safe_text(dry_run_manifest_path),
        "allowlist_id": _safe_text(allowlist_id),
        "allowlist_manifest_path": _safe_text(allowlist_manifest_path),
        "risk_level": _safe_text(risk_level, "unknown"),
        "status": _safe_status(status),
        "runtime_level": RUNTIME_LEVEL,
        "manual_only": True,
        "one_action_only": True,
        "loop_enabled": False,
        "auto_continue_enabled": False,
        "execution_enabled": False,
        "level1_execution_enabled": False,
        "autonomous_execution_enabled": False,
        "execution_performed": False,
        "mutation_performed": False,
        "verification_performed": False,
        "rollback_performed": False,
        "retry_performed": False,
        "remote_git_operation_performed": False,
        "backend_authoritative": True,
        "vue_authoritative": False,
        "warnings": [
            "SCALE-122 captures execution artifact metadata only.",
            "No command execution, mutation, verification, rollback, retry, remote git operation, or loop continuation was performed.",
            *_safe_list(warnings),
        ],
        "policy_notes": [
            "scale_122_execution_artifact_capture_v1",
            "metadata_only",
            "one_action_only",
            "no_loop",
            "no_execution_performed",
            *_safe_list(policy_notes),
        ],
        "next_required_pr": "PR-ATLAS-SCALE-123",
    }
    validate_level1_execution_artifact_manifest(manifest)
    return manifest


def validate_level1_execution_artifact_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    required = [
        "artifact_id",
        "schema_version",
        "created_at",
        "run_id",
        "action_id",
        "runtime_level",
        "manual_only",
        "one_action_only",
        "loop_enabled",
        "auto_continue_enabled",
        "execution_enabled",
        "level1_execution_enabled",
        "autonomous_execution_enabled",
        "execution_performed",
        "mutation_performed",
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
        "one_action_only": manifest.get("one_action_only") is True,
        "loop_enabled": manifest.get("loop_enabled") is False,
        "auto_continue_enabled": manifest.get("auto_continue_enabled") is False,
        "execution_enabled": manifest.get("execution_enabled") is False,
        "level1_execution_enabled": manifest.get("level1_execution_enabled") is False,
        "autonomous_execution_enabled": manifest.get("autonomous_execution_enabled") is False,
        "execution_performed": manifest.get("execution_performed") is False,
        "mutation_performed": manifest.get("mutation_performed") is False,
        "verification_performed": manifest.get("verification_performed") is False,
        "rollback_performed": manifest.get("rollback_performed") is False,
        "retry_performed": manifest.get("retry_performed") is False,
        "remote_git_operation_performed": manifest.get("remote_git_operation_performed") is False,
        "backend_authoritative": manifest.get("backend_authoritative") is True,
        "vue_authoritative": manifest.get("vue_authoritative") is False,
    }
    violations = [key for key, ok in invariants.items() if not ok]
    if violations:
        raise ValueError(f"invariant_violation:{','.join(sorted(violations))}")
    return manifest


def write_level1_execution_artifact_manifest(*, data_root: str | Path, manifest: dict[str, Any]) -> Path:
    validated = validate_level1_execution_artifact_manifest(manifest)
    root = Path(data_root).expanduser().resolve()
    artifact_id = str(validated["artifact_id"])
    manifest_path = root / "atlas" / "level1_execution_artifacts" / artifact_id / "manifest.json"
    _ensure_under(root, manifest_path, "manifest_outside_data_root")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(validated, indent=2, sort_keys=True), encoding="utf-8")
    return manifest_path


def load_level1_execution_artifact_manifest(*, manifest_path: str | Path, data_root: str | Path | None = None) -> dict[str, Any]:
    path = Path(manifest_path).expanduser().resolve()
    if data_root is not None:
        _ensure_under(Path(data_root).expanduser().resolve(), path, "manifest_outside_data_root")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return validate_level1_execution_artifact_manifest(payload)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _artifact_id(*, run_id: str, action_id: str, created_at: str) -> str:
    created_norm = created_at.replace(":", "").replace("-", "").replace("+", "").replace(".", "")
    return f"exec_{_safe_text(run_id, 'run')}_{_safe_text(action_id, 'action')}_{created_norm}"


def _safe_status(value: str) -> str:
    text = _safe_text(value, "not_executed")
    return text if text in {"not_executed", "blocked", "captured_external_reference"} else "not_executed"


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
