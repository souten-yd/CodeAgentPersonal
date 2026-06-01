from __future__ import annotations

from datetime import datetime, timezone

from agent.atlas_failure_stop_schema import AtlasFailureStopSuggestion

# Mirror of the autopilot service's priority (kept local to avoid an import cycle, since the
# autopilot service imports this module). Picks the dominant actionable verification marker so
# the recovery proposal surfaces *why* verification failed.
_VERIFICATION_REASON_PRIORITY = (
    "browser_smoke_failed:",
    "visual_contract_failed",
    "visual_missing:",
    "test_harness_unavailable",
    "pytest_not_installed",
)


def _primary_verification_reason(verification_result: dict) -> str:
    warnings = [str(w) for w in ((verification_result or {}).get("warnings") or [])]
    for prefix in _VERIFICATION_REASON_PRIORITY:
        for w in warnings:
            if w == prefix or w.startswith(prefix):
                return w
    for w in warnings:
        if w == "visual_contract_passed" or w.startswith("browser_smoke_warning"):
            continue
        return w
    return ""


class AtlasFailureStopService:
    def __init__(self, *, journal):
        self.journal = journal

    def build_for_verification_failure(self, pool, item, run_id: str, verification_result: dict) -> AtlasFailureStopSuggestion:
        verification_status = str((verification_result or {}).get("status") or "").lower()
        if verification_status != "failed":
            return AtlasFailureStopSuggestion(pool_id=pool.pool_id, item_id=item.item_id, run_id=run_id, failure_phase="auto_verification", status="no_action", reason="verification_not_failed", verification_result=dict(verification_result or {}))

        metadata = dict(getattr(item, "metadata", {}) or {})
        safe_apply_meta = metadata.get("safe_apply") or {}
        auto_safe_meta = metadata.get("auto_safe_apply") or {}
        snapshot = auto_safe_meta.get("change_snapshot") or safe_apply_meta.get("change_snapshot") or {}
        manifest_path = str(snapshot.get("manifest_path") or "")
        changed_files = list(snapshot.get("changed_files") or [])
        restore_candidate = {
            "manifest_path": manifest_path,
            "snapshot_id": str(snapshot.get("snapshot_id") or ""),
            "workspace_root": str(snapshot.get("workspace_root") or ""),
            "changed_files": changed_files,
            "file_count": snapshot.get("file_count"),
        } if manifest_path else {}
        primary_reason = _primary_verification_reason(verification_result)
        smoke = (((verification_result or {}).get("metadata") or {}).get("browser_smoke") or {})
        console_errors = list(smoke.get("console_errors") or [])[:10] if isinstance(smoke, dict) else []
        manual_actions = [
            "Review verification failure.",
            "Inspect changed files.",
            "Restore from Change Snapshot manually if needed.",
            "Run Debug Review manually if restore is not desired.",
        ]
        if primary_reason:
            manual_actions.insert(0, f"Verification failed: {primary_reason}")
        suggestion = AtlasFailureStopSuggestion(
            pool_id=pool.pool_id,
            item_id=item.item_id,
            run_id=run_id,
            failure_phase="auto_verification",
            status="stopped",
            reason="auto_verification_failed_after_safe_apply",
            suggested_manual_actions=manual_actions,
            restore_candidate=restore_candidate,
            snapshot_manifest_path=manifest_path,
            changed_files=changed_files,
            verification_result=dict(verification_result or {}),
            metadata={"has_restore_candidate": bool(manifest_path), "primary_verification_reason": primary_reason, "console_errors": console_errors},
        )
        if run_id:
            self.journal.append_event(pool.pool_id, run_id, {
                "event_type": "automation_stopped_after_verification_failure",
                "pool_id": pool.pool_id,
                "run_id": run_id,
                "item_id": item.item_id,
                "status": "stopped",
                "warnings": [],
                "errors": [],
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        return suggestion
