from __future__ import annotations

from datetime import datetime, timezone

from agent.atlas_failure_stop_schema import AtlasFailureStopSuggestion


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
        suggestion = AtlasFailureStopSuggestion(
            pool_id=pool.pool_id,
            item_id=item.item_id,
            run_id=run_id,
            failure_phase="auto_verification",
            status="stopped",
            reason="auto_verification_failed_after_safe_apply",
            suggested_manual_actions=[
                "Review verification failure.",
                "Inspect changed files.",
                "Restore from Change Snapshot manually if needed.",
                "Run Debug Review manually if restore is not desired.",
            ],
            restore_candidate=restore_candidate,
            snapshot_manifest_path=manifest_path,
            changed_files=changed_files,
            verification_result=dict(verification_result or {}),
            metadata={"has_restore_candidate": bool(manifest_path)},
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
