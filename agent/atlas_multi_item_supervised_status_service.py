from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from agent.atlas_dev_tool_path import validate_relative_path
from agent.atlas_multi_item_supervised_status_policies import get_multi_item_supervised_status_policy
from agent.atlas_multi_item_supervised_status_schema import AtlasMultiItemSupervisedItemSummary, AtlasMultiItemSupervisedStatusRequest, AtlasMultiItemSupervisedStatusResult
from agent.atlas_supervised_item_status_schema import AtlasSupervisedItemStatusFinalizeRequest


class AtlasMultiItemSupervisedStatusService:
    def __init__(self, *, storage, journal, supervised_item_status_service):
        self.storage = storage
        self.journal = journal
        self.supervised_item_status_service = supervised_item_status_service

    def _event_payload(self, req, msid, *, item_count=0, selected_count=0, refreshed_count=0, failed_count=0, next_item_id="", next_action="", counts=None, warning_count=0, error_count=0):
        rid = req.run_id or msid
        return {
            "multi_status_run_id": msid,
            "pool_id": req.pool_id,
            "run_id": rid,
            "item_count": item_count,
            "selected_count": selected_count,
            "refreshed_count": refreshed_count,
            "failed_count": failed_count,
            "next_item_id": next_item_id,
            "next_action": next_action,
            "counts": counts or {},
            "warning_count": warning_count,
            "error_count": error_count,
            "next_action_executed": False,
            "safe_apply_executed": False,
            "verification_executed": False,
            "bounded_retry_executed": False,
            "patch_regeneration_executed": False,
            "approval_executed": False,
            "rollback_executed": False,
            "restore_executed": False,
            "debug_review_executed": False,
        }

    def _emit(self, event_type, req, msid, **kw):
        payload = self._event_payload(req, msid, **kw)
        payload.update({"event_type": event_type, "created_at": datetime.now(timezone.utc).isoformat()})
        self.journal.append_event(req.pool_id, payload["run_id"], payload)

    def validate_next_action_payload(self, summary: AtlasMultiItemSupervisedItemSummary):
        required_map = {
            "approve_patch_candidate": ["regen_run_id", "proposal_id"],
            "run_supervised_safe_apply": ["handoff_id"],
            "run_supervised_verification": ["safe_apply_execution_id"],
            "run_supervised_retry": ["verification_run_id", "safe_apply_execution_id"],
            "run_patch_regen_from_recommendation": ["recommendation_run_id"],
        }
        blocked_reason_map = {
            "approve_patch_candidate": "missing_approval_payload",
            "run_supervised_safe_apply": "missing_safe_apply_handoff_id",
            "run_supervised_verification": "missing_safe_apply_execution_id",
            "run_supervised_retry": "missing_retry_payload",
            "run_patch_regen_from_recommendation": "missing_recommendation_run_id",
        }
        payload = summary.next_action_payload or {}
        required_fields = required_map.get(summary.next_action, [])
        missing = [k for k in required_fields if not payload.get(k)]
        summary.metadata["payload_validated"] = True
        summary.metadata["payload_required_fields"] = required_fields
        summary.metadata["payload_missing_fields"] = missing
        if summary.next_action == "run_supervised_verification" and not payload.get("handoff_id"):
            summary.warnings.append("missing_handoff_id")
        if missing:
            summary.selectable = False
            summary.blocked_reason = blocked_reason_map.get(summary.next_action, "missing_next_action_payload")

    def build_status(self, request: AtlasMultiItemSupervisedStatusRequest):
        policy = get_multi_item_supervised_status_policy(request.policy_id)
        msid = f"multistatus_{uuid4().hex[:10]}"
        pool = self.storage.load_pool(request.pool_id)
        source_ids = request.item_ids or [i.item_id for i in pool.items]
        max_count = min(request.max_items, policy.max_items)
        ids = source_ids[:max_count]
        warnings = []
        errors = []
        refreshed_count = 0
        failed_count = 0
        self._emit("multi_item_supervised_status_started", request, msid, item_count=len(ids), selected_count=len(ids))
        if request.item_ids and ids and all(pool.get_item(i) is None for i in ids):
            warnings.append("all_requested_items_missing")
        sums = []
        for iid in ids:
            try:
                validate_relative_path(iid)
            except Exception:
                warnings.append(f"invalid_item_id:{iid}")
                continue
            item = pool.get_item(iid)
            if not item:
                warnings.append(f"missing_item_id:{iid}")
                continue
            fin = None
            if request.refresh_item_status and policy.refresh_item_status:
                try:
                    fin = self.supervised_item_status_service.finalize(AtlasSupervisedItemStatusFinalizeRequest(pool_id=request.pool_id, item_id=iid, run_id=request.run_id or msid, workspace_id=request.workspace_id, project_path=request.project_path, policy_id="supervised_item_status_v1", use_latest_artifacts=request.use_latest_artifacts, update_item_status=(request.update_item_status and not request.dry_run and policy.update_item_status), update_metadata=(request.update_metadata and not request.dry_run), dry_run=(request.dry_run or not policy.update_item_status), reviewer=request.reviewer, reason=request.reason, metadata={"source": "multi_item_supervised_status", "multi_status_run_id": msid}))
                    refreshed_count += 1
                    self._emit("multi_item_supervised_status_item_refreshed", request, msid, item_count=len(ids), selected_count=len(ids), refreshed_count=refreshed_count)
                except Exception as ex:
                    failed_count += 1
                    errors.append(f"finalize_failed:{iid}:{ex}")
                    self._emit("multi_item_supervised_status_item_failed", request, msid, item_count=len(ids), selected_count=len(ids), failed_count=failed_count)
            md = item.metadata or {}
            sup = md.get("supervised_item_status") or {}
            status = (fin.transition.to_status if fin else sup.get("status") or item.status or "unchanged")
            action = (fin.next_action if fin else sup.get("next_action") or "manual_review")
            payload = (fin.next_action_payload if fin else sup.get("next_action_payload") or {})
            s = AtlasMultiItemSupervisedItemSummary(item_id=iid, item_title=str(getattr(item, "title", "") or getattr(item, "name", "") or getattr(item, "description", ""))[:120], item_status=str(item.status or ""), supervised_status=str(status), next_action=str(action), next_action_payload=payload if request.include_next_action_payloads else {}, evidence_type=str((fin.transition.evidence_type if fin else sup.get("evidence_type")) or ""), evidence_run_id=str((fin.transition.evidence_run_id if fin else sup.get("evidence_run_id")) or ""))
            self.validate_next_action_payload(s)
            sums.append(s)

        self._emit("multi_item_supervised_status_items_selected", request, msid, item_count=len(source_ids), selected_count=len(ids), refreshed_count=refreshed_count, failed_count=failed_count)
        if not sums:
            warnings.append("no_items_selected")

        pri = {"approve_patch_candidate": 10, "run_supervised_safe_apply": 20, "run_supervised_verification": 30, "run_supervised_retry": 40, "run_patch_regen_from_recommendation": 50, "manual_review": 80, "investigate_failure": 90, "none": 1000}
        groups = {k: [] for k in ["approve_patch_candidate", "run_supervised_safe_apply", "run_supervised_verification", "run_supervised_retry", "run_patch_regen_from_recommendation", "manual_review", "investigate_failure", "none"]}
        for s in sums:
            s.priority = pri.get(s.next_action, 900) + (500 if not s.selectable else 0)
            groups.setdefault(s.next_action, []).append(s.item_id)

        ordered = sorted([s for s in sums if s.selectable and s.supervised_status not in {"completed", "failed_internal"}], key=lambda x: x.priority)
        next_item = ordered[0] if ordered else None
        counts = {}
        for s in sums:
            counts[s.supervised_status] = counts.get(s.supervised_status, 0) + 1

        unselectable_count = len([s for s in sums if not s.selectable])
        payload_validation_summary = {k: 0 for k in ["missing_approval_payload", "missing_safe_apply_handoff_id", "missing_safe_apply_execution_id", "missing_retry_payload", "missing_recommendation_run_id"]}
        for s in sums:
            if s.blocked_reason in payload_validation_summary:
                payload_validation_summary[s.blocked_reason] += 1

        if not sums or len(ids) == 0:
            status = "blocked"
        elif request.dry_run:
            status = "dry_run"
        elif errors:
            status = "partial"
        elif next_item is None:
            status = "blocked"
        else:
            status = "ready"

        if next_item:
            self._emit("multi_item_supervised_status_ready", request, msid, item_count=len(source_ids), selected_count=len(ids), refreshed_count=refreshed_count, failed_count=failed_count, next_item_id=next_item.item_id, next_action=next_item.next_action, counts=counts, warning_count=len(warnings), error_count=len(errors))
        else:
            self._emit("multi_item_supervised_status_blocked", request, msid, item_count=len(source_ids), selected_count=len(ids), refreshed_count=refreshed_count, failed_count=failed_count, counts=counts, warning_count=len(warnings), error_count=len(errors))
        self._emit("multi_item_supervised_status_ranked", request, msid, item_count=len(source_ids), selected_count=len(ids), refreshed_count=refreshed_count, failed_count=failed_count, next_item_id=(next_item.item_id if next_item else ""), next_action=(next_item.next_action if next_item else ""), counts=counts, warning_count=len(warnings), error_count=len(errors))

        side_effects = {"next_action_executed": False, "safe_apply_executed": False, "verification_executed": False, "bounded_retry_executed": False, "patch_regeneration_executed": False, "approval_executed": False, "rollback_executed": False, "restore_executed": False, "debug_review_executed": False}
        res = AtlasMultiItemSupervisedStatusResult(pool_id=request.pool_id, run_id=request.run_id, multi_status_run_id=msid, policy_id=policy.policy_id, status=status, item_summaries=sums, next_item=next_item, next_actions_by_type=groups, counts=counts, warnings=warnings, errors=errors, metadata={"supervised_status_integrated": True, "queue_only": True, "next_action_executed": False, "next_item_id": (next_item.item_id if next_item else ""), "next_action": (next_item.next_action if next_item else ""), "counts": counts, "selected_count": len(ids), "refreshed_count": refreshed_count, "failed_count": failed_count, "unselectable_count": unselectable_count, "payload_validation_summary": payload_validation_summary, "side_effects": side_effects, **side_effects})

        root = Path("ca_data") / "atlas" / "multi_item_supervised_status" / request.pool_id
        root.mkdir(parents=True, exist_ok=True)
        (root / f"{msid}.json").write_text(json.dumps(res.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")

        lines = ["# Multi-item Supervised Status", "", "## Summary", f"- multi_status_run_id: {msid}", f"- pool_id: {request.pool_id}", f"- status: {status}", f"- next_item_id: {next_item.item_id if next_item else ''}", f"- next_action: {next_item.next_action if next_item else ''}", "", "## Counts"]
        for k in ["completed", "patch_candidate_ready", "safe_apply_ready", "verification_required", "patch_regen_recommended", "needs_revision", "manual_required", "blocked", "failed_internal", "unchanged"]:
            lines.append(f"- {k}: {counts.get(k, 0)}")
        lines += ["", "## Next Item"]
        if next_item:
            lines += [f"- item_id: {next_item.item_id}", f"- supervised_status: {next_item.supervised_status}", f"- next_action: {next_item.next_action}", f"- next_action_payload summary: {', '.join(sorted((next_item.next_action_payload or {}).keys()))}", f"- evidence_type: {next_item.evidence_type}", f"- evidence_run_id: {next_item.evidence_run_id}"]
        else:
            lines.append("- (none)")
        lines += ["", "## Action Queue"]
        for k, v in groups.items():
            lines.append(f"- {k}: {len(v)}")
        lines.append(f"- unselectable_count: {unselectable_count}")
        lines += ["", "## Payload Validation"] + [f"- {k}: {v}" for k, v in payload_validation_summary.items()] + ["", "## Safety", "- next action executed: false", "- safe_apply executed: false", "- verification executed: false", "- bounded retry executed: false", "- patch regeneration executed: false", "- approval executed: false", "- rollback/restore/debug executed: false"]
        (root / f"{msid}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

        self._emit("multi_item_supervised_status_result_saved", request, msid, item_count=len(source_ids), selected_count=len(ids), refreshed_count=refreshed_count, failed_count=failed_count, next_item_id=(next_item.item_id if next_item else ""), next_action=(next_item.next_action if next_item else ""), counts=counts, warning_count=len(warnings), error_count=len(errors))
        return res
