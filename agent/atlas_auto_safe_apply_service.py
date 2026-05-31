from __future__ import annotations

from datetime import datetime, timezone

from agent.atlas_auto_policy_presets import atlas_auto_policy_presets
from agent.atlas_auto_safe_apply_schema import AtlasAutoSafeApplyRequest, AtlasAutoSafeApplyResult
from agent.atlas_plan_item_file_changes import normalize_plan_item_file_changes
from agent.atlas_safe_apply_execution_schema import AtlasSafeApplyExecutionRequest


class AtlasAutoSafeApplyService:
    def __init__(self, *, automation_gate, safe_apply_service, journal, storage):
        self.automation_gate = automation_gate
        self.safe_apply_service = safe_apply_service
        self.journal = journal
        self.storage = storage

    def execute_one(self, request: AtlasAutoSafeApplyRequest) -> AtlasAutoSafeApplyResult:
        pool = self.storage.load_pool(request.pool_id)
        item = pool.get_item(request.item_id)
        if item is None:
            return AtlasAutoSafeApplyResult(pool_id=request.pool_id, item_id=request.item_id, run_id=request.run_id, preset_id=request.preset_id, status="blocked", warnings=["item_not_found"]) 

        preset = atlas_auto_policy_presets().get(request.preset_id)
        if preset is None:
            return AtlasAutoSafeApplyResult(pool_id=request.pool_id, item_id=request.item_id, run_id=request.run_id, preset_id=request.preset_id, status="failed", errors=["preset_not_found"])

        norm = normalize_plan_item_file_changes(item)
        if norm.get("changed"):
            self.storage.save_pool(pool)
            self.journal.save_plan_pool(pool)
        decision = self.automation_gate.decide_pre_safe_apply(pool, item, preset)
        self._append_event(pool.pool_id, request.run_id, "auto_safe_apply_decision", item.item_id, status=decision.decision, warnings=list(decision.warnings), errors=list(decision.reasons))

        if request.dry_run_decision_only:
            return AtlasAutoSafeApplyResult(pool_id=pool.pool_id, item_id=item.item_id, run_id=request.run_id, preset_id=request.preset_id, status="decision_only", automation_decision=decision.model_dump(), plan_pool=pool.model_dump(), warnings=list(decision.warnings), errors=list(decision.reasons))

        if decision.decision != "allow":
            status = "skipped" if decision.decision == "require_manual" else "blocked"
            self._append_event(pool.pool_id, request.run_id, "auto_safe_apply_blocked", item.item_id, status=status, warnings=list(decision.warnings), errors=list(decision.reasons))
            return AtlasAutoSafeApplyResult(pool_id=pool.pool_id, item_id=item.item_id, run_id=request.run_id, preset_id=request.preset_id, status=status, automation_decision=decision.model_dump(), plan_pool=pool.model_dump(), warnings=list(decision.warnings), errors=list(decision.reasons))

        self._append_event(pool.pool_id, request.run_id, "auto_safe_apply_started", item.item_id, status="started")
        safe_metadata = {**dict(request.metadata or {}), "preset_id": request.preset_id}
        safe = self.safe_apply_service.execute_item(AtlasSafeApplyExecutionRequest(pool_id=pool.pool_id, item_id=item.item_id, run_id=request.run_id, workspace_id=request.workspace_id, requested_by="atlas_auto_safe_apply", dry_run=False, metadata=safe_metadata))
        safe_payload = safe.model_dump()
        snapshot = ((safe_payload.get("metadata") or {}).get("change_snapshot") or (safe_payload.get("safe_apply_result") or {}).get("change_snapshot") or {})
        changed = bool(((safe_payload.get("metadata") or {}).get("executor_result") or {}).get("actual_file_changed", safe_payload.get("safe_apply_result", {}).get("actual_file_changed", False)))
        changed_files = list(((safe_payload.get("metadata") or {}).get("executor_result") or {}).get("changed_files") or safe_payload.get("safe_apply_result", {}).get("changed_files") or [])
        file_results = list(((safe_payload.get("metadata") or {}).get("executor_result") or {}).get("file_results") or safe_payload.get("safe_apply_result", {}).get("file_results") or [])
        final_status = str(safe_payload.get("status") or "failed")
        warnings = list(safe_payload.get("warnings") or [])
        errors = list(safe_payload.get("errors") or [])

        if final_status == "applied" and not snapshot.get("manifest_path"):
            final_status = "failed"
            errors.append("snapshot_manifest_missing")
        if final_status == "applied" and not changed:
            final_status = "failed"
            errors.append("actual_file_not_changed")

        event_type = "auto_safe_apply_completed" if final_status == "applied" else ("auto_safe_apply_blocked" if final_status in {"blocked", "skipped"} else "auto_safe_apply_failed")
        self._append_event(pool.pool_id, request.run_id, event_type, item.item_id, status=final_status, warnings=warnings, errors=errors)

        metadata = dict(safe_payload.get("metadata") or {})
        metadata["file_results"] = file_results
        return AtlasAutoSafeApplyResult(pool_id=pool.pool_id, item_id=item.item_id, run_id=request.run_id, preset_id=request.preset_id, status="applied" if final_status == "applied" else ("blocked" if final_status in {"blocked", "skipped"} else "failed"), automation_decision=decision.model_dump(), safe_apply_result=safe_payload.get("safe_apply_result") or {}, change_snapshot=snapshot, workspace_root=str((safe_payload.get("metadata") or {}).get("workspace_root") or ""), actual_file_changed=changed, changed_files=changed_files, warnings=warnings, errors=errors, metadata=metadata, plan_pool=safe_payload.get("plan_pool"))

    def _append_event(self, pool_id: str, run_id: str, event_type: str, item_id: str, *, status: str, warnings: list[str] | None = None, errors: list[str] | None = None):
        if not run_id:
            return
        self.journal.append_event(pool_id, run_id, {"event_type": event_type, "pool_id": pool_id, "run_id": run_id, "item_id": item_id, "status": status, "warnings": list(warnings or []), "errors": list(errors or []), "created_at": datetime.now(timezone.utc).isoformat()})
