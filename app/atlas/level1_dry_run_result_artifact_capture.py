from __future__ import annotations

from pathlib import Path
from typing import Any

from app.atlas.dry_run_artifact_schema import (
    create_dry_run_artifact_manifest,
    write_dry_run_artifact_manifest,
)
from app.atlas.level1_dry_run_endpoint_skeleton import RUNTIME_LEVEL


CAPTURE_SCHEMA_VERSION = "atlas.level1_dry_run_result_artifact_capture.v1"


def capture_level1_dry_run_result_artifact(
    *,
    data_root: str | Path,
    dry_run_result: dict[str, Any],
) -> dict[str, Any]:
    """Persist a dry-run result artifact reference without executing anything."""

    result = dict(dry_run_result or {})
    manifest = create_dry_run_artifact_manifest(
        workspace_id=_safe_text(result.get("workspace_id"), "default"),
        pool_id=_safe_text(result.get("pool_id"), ""),
        item_id=_safe_text(result.get("item_id"), ""),
        run_id=_safe_text(result.get("run_id"), "level1_dry_run"),
        action_id=_safe_text(result.get("action_id"), "dry_run_only"),
        command_summary=_safe_text(
            result.get("dry_run_summary") or result.get("command_summary"),
            "Captured Level-1 dry-run-only result metadata.",
        ),
        allowlist_reference=_safe_text(result.get("allowlist_reference"), "not_executed"),
        risk_level=_safe_text(result.get("risk_level"), "unknown"),
        expected_artifacts=_safe_list(result.get("expected_artifacts")),
        verification_targets=_safe_list(result.get("verification_targets")),
        rollback_reference=_safe_text(result.get("rollback_reference"), "manual_only"),
        stop_conditions=_safe_list(result.get("stop_conditions")) or ["manual_stop"],
        policy_notes=[
            "scale_118_dry_run_result_artifact_capture",
            "capture_only",
            "no_execution",
            *_safe_list(result.get("policy_notes")),
        ],
        warnings=[
            "Captured dry-run result artifact metadata only.",
            "No execution, mutation, verification, rollback, retry, or remote git operation was performed.",
            *_safe_list(result.get("warnings")),
        ],
        created_at=_safe_optional_text(result.get("created_at")),
    )
    manifest_path = write_dry_run_artifact_manifest(data_root=data_root, manifest=manifest)
    return {
        "schema_version": CAPTURE_SCHEMA_VERSION,
        "status": "captured",
        "artifact_id": manifest["artifact_id"],
        "manifest_path": str(manifest_path),
        "manifest": manifest,
        "runtime_level": RUNTIME_LEVEL,
        "manual_only": True,
        "dry_run_only": True,
        "capture_only": True,
        "mutation_performed": False,
        "execution_performed": False,
        "verification_performed": False,
        "rollback_performed": False,
        "retry_performed": False,
        "remote_git_operation_performed": False,
        "level1_execution_enabled": False,
        "autonomous_execution_enabled": False,
        "next_required_pr": "PR-ATLAS-SCALE-119",
    }


def _safe_text(value: Any, fallback: str) -> str:
    if isinstance(value, str):
        text = value.strip()
        if text:
            return text[:512]
    return fallback


def _safe_optional_text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _safe_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip()[:512] for item in value if isinstance(item, str) and item.strip()]
