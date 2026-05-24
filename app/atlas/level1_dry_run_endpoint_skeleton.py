from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


SCHEMA_VERSION = "atlas.level1_dry_run_endpoint_skeleton.v1"
RUNTIME_LEVEL = "level_0_manual_only"


def build_level1_dry_run_only_result(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a non-mutating Level-1 dry-run-only endpoint response."""

    request = dict(payload or {})
    workspace_id = _safe_text(request.get("workspace_id"), "default")
    pool_id = _safe_text(request.get("pool_id"), "")
    item_id = _safe_text(request.get("item_id"), "")
    action_id = _safe_text(request.get("action_id"), "")
    command_id = _safe_text(request.get("command_id"), "")
    risk_level = _safe_text(request.get("risk_level"), "unknown")
    dry_run_summary = _safe_text(
        request.get("dry_run_summary"),
        "Level-1 dry-run-only skeleton accepted metadata for review.",
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "dry_run_only_skeleton",
        "created_at": datetime.now(UTC).isoformat(),
        "workspace_id": workspace_id,
        "pool_id": pool_id,
        "item_id": item_id,
        "action_id": action_id,
        "command_id": command_id,
        "risk_level": risk_level,
        "dry_run_summary": dry_run_summary,
        "runtime_level": RUNTIME_LEVEL,
        "manual_only": True,
        "dry_run_only": True,
        "advisory_only": True,
        "backend_authoritative": True,
        "vue_authoritative": False,
        "mutation_performed": False,
        "execution_performed": False,
        "artifact_persisted": False,
        "level1_execution_enabled": False,
        "autonomous_execution_enabled": False,
        "automatic_verification_enabled": False,
        "automatic_patch_apply_enabled": False,
        "automatic_retry_enabled": False,
        "automatic_rollback_enabled": False,
        "remote_git_operations_enabled": False,
        "requires_followup_artifact_capture": True,
        "next_required_pr": "PR-ATLAS-SCALE-118",
        "blocked_actions": [
            "execute",
            "apply_patch",
            "verify",
            "retry",
            "rollback",
            "auto_continue",
            "remote_git",
        ],
        "warnings": [
            "SCALE-117 is a dry-run-only backend endpoint skeleton.",
            "No mutation, execution, persistence, verification, rollback, retry, or remote git operation was performed.",
        ],
    }


def _safe_text(value: Any, fallback: str) -> str:
    if isinstance(value, str):
        text = value.strip()
        if text:
            return text[:512]
    return fallback
