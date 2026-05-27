from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_latest_practical_loop_workflow_metadata(*, data_root: str | Path) -> dict[str, Any]:
    root = Path(data_root).expanduser().resolve()
    loop_root = root / "atlas" / "guarded_operator_loop"
    if not loop_root.exists():
        return _empty_metadata(source_detail="no_guarded_loop_artifacts")

    candidates = [path for path in loop_root.glob("*/guardloop_*.json") if _is_safe_file(root, path)]
    if not candidates:
        return _empty_metadata(source_detail="no_guarded_loop_artifacts")

    latest = max(candidates, key=lambda path: path.stat().st_mtime)
    try:
        payload = json.loads(latest.read_text(encoding="utf-8"))
    except Exception:
        return _empty_metadata(source_detail="latest_guarded_loop_artifact_unreadable")

    if not isinstance(payload, dict):
        return _empty_metadata(source_detail="latest_guarded_loop_artifact_invalid")

    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    dry_run_result = payload.get("dry_run_result") if isinstance(payload.get("dry_run_result"), dict) else {}
    execute_result = payload.get("execute_result") if isinstance(payload.get("execute_result"), dict) else {}
    refresh_result = payload.get("refresh_result") if isinstance(payload.get("refresh_result"), dict) else {}
    steps = payload.get("steps") if isinstance(payload.get("steps"), list) else []
    status = _text(payload.get("status"), "metadata_only")
    changed_count = _first_int(
        refresh_result.get("changed_file_count"),
        execute_result.get("changed_file_count"),
        dry_run_result.get("changed_file_count"),
        metadata.get("changed_file_count"),
        default=0,
    )
    executed = bool(metadata.get("confirmed_action_executed"))
    dry_run_ready = status in {"dry_run_ready", "executed", "executed_and_refreshed"} or bool(dry_run_result)
    recovery_state = _text(metadata.get("recovery_state"), "not_started")
    if payload.get("errors"):
        recovery_state = "needs_review"

    latest_recovery_run_id = _text(payload.get("post_refresh_run_id"), "")
    latest_draft_pr_artifact_id = _text(metadata.get("latest_draft_pr_artifact_id"), "")
    recovery_artifact_available = bool(latest_recovery_run_id or refresh_result)
    draft_pr_artifact_available = bool(latest_draft_pr_artifact_id)

    return {
        "practical_loop_status": status,
        "bounded_loop": True,
        "max_iterations": _first_int(metadata.get("max_auto_steps_per_request"), metadata.get("max_iterations"), default=1),
        "current_iteration": max(1, len(steps)) if steps else 1,
        "stop_condition": "manual_review_or_backend_gate",
        "patch_candidate_count": changed_count,
        "verification_state": "dry_run_metadata_available" if dry_run_ready else "waiting_for_backend_checks",
        "recovery_state": recovery_state,
        "draft_pr_state": _text(metadata.get("draft_pr_state"), "not_prepared"),
        "latest_loop_run_id": _text(payload.get("loop_run_id"), ""),
        "latest_recovery_run_id": latest_recovery_run_id,
        "latest_draft_pr_artifact_id": latest_draft_pr_artifact_id,
        "latest_loop_pool_id": _text(payload.get("pool_id"), ""),
        "latest_loop_mode": _text(payload.get("mode"), ""),
        "latest_loop_result_path": str(latest.relative_to(root).as_posix()),
        "latest_loop_action_executed": executed,
        "latest_loop_source_detail": "safe_latest_guarded_loop_artifact",
        "recovery_artifact_available": recovery_artifact_available,
        "recovery_artifact_summary": _artifact_summary(
            explicit=metadata.get("recovery_artifact_summary"),
            available=recovery_artifact_available,
            prefix="recovery",
            identifier=latest_recovery_run_id,
            state=recovery_state,
        ),
        "draft_pr_artifact_available": draft_pr_artifact_available,
        "draft_pr_artifact_summary": _artifact_summary(
            explicit=metadata.get("draft_pr_artifact_summary"),
            available=draft_pr_artifact_available,
            prefix="draft_pr",
            identifier=latest_draft_pr_artifact_id,
            state=_text(metadata.get("draft_pr_state"), "not_prepared"),
        ),
    }


def _empty_metadata(*, source_detail: str) -> dict[str, Any]:
    return {
        "practical_loop_status": "metadata_only",
        "bounded_loop": False,
        "max_iterations": 0,
        "current_iteration": 0,
        "stop_condition": "manual_review_or_backend_gate",
        "patch_candidate_count": 0,
        "verification_state": "waiting_for_backend_checks",
        "recovery_state": "unknown",
        "draft_pr_state": "not_prepared",
        "latest_loop_run_id": "",
        "latest_recovery_run_id": "",
        "latest_draft_pr_artifact_id": "",
        "latest_loop_pool_id": "",
        "latest_loop_mode": "",
        "latest_loop_result_path": "",
        "latest_loop_action_executed": False,
        "latest_loop_source_detail": source_detail,
        "recovery_artifact_available": False,
        "recovery_artifact_summary": "not_available",
        "draft_pr_artifact_available": False,
        "draft_pr_artifact_summary": "not_available",
    }


def _is_safe_file(root: Path, path: Path) -> bool:
    try:
        resolved = path.resolve()
        resolved.relative_to(root)
    except ValueError:
        return False
    return resolved.is_file() and resolved.name.startswith("guardloop_") and resolved.suffix == ".json"


def _text(value: Any, fallback: str) -> str:
    return value if isinstance(value, str) and value.strip() else fallback


def _first_int(*values: Any, default: int = 0) -> int:
    for value in values:
        if isinstance(value, bool):
            continue
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            continue
    return default


def _artifact_summary(*, explicit: Any, available: bool, prefix: str, identifier: str, state: str) -> str:
    if isinstance(explicit, str) and explicit.strip():
        return explicit
    if available:
        suffix = identifier or state or "available"
        return f"{prefix}:{suffix}"
    return "not_available"
