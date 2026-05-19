from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agent.atlas_journal import AtlasJournal
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_supervised_item_status_policies import get_supervised_item_status_policy
from agent.atlas_supervised_item_status_schema import AtlasSupervisedItemStatusFinalizeRequest, AtlasSupervisedItemStatusFinalizeResult, AtlasSupervisedItemTransition


class AtlasSupervisedItemStatusService:
    def __init__(self, *, storage=None, journal=None):
        self.storage = storage or AtlasPlanPoolStorage(Path("ca_data"))
        self.journal = journal or AtlasJournal(Path("ca_data"))

    def finalize(self, request: AtlasSupervisedItemStatusFinalizeRequest) -> AtlasSupervisedItemStatusFinalizeResult:
        finalize_id = f"itemstatus_{uuid4().hex[:12]}"
        rid = request.run_id or finalize_id
        policy = get_supervised_item_status_policy(request.policy_id)
        pool = self.storage.load_pool(request.pool_id); item = pool.get_item(request.item_id)
        if item is None:
            t = AtlasSupervisedItemTransition(to_status="blocked", reason="item_not_found", next_action="investigate_failure", errors=["item_not_found"])
            return AtlasSupervisedItemStatusFinalizeResult(pool_id=request.pool_id,item_id=request.item_id,run_id=rid,finalize_run_id=finalize_id,policy_id=policy.policy_id,status="blocked",transition=t,errors=["item_not_found"])
        ev = self.collect_evidence(item.metadata or {})
        to_status, reason, next_action, etype, erun = self.decide_transition(ev)
        payload = self.build_next_action_payload(request, ev, next_action)
        t = AtlasSupervisedItemTransition(from_status=str(item.status or ""),to_status=to_status,reason=reason,next_action=next_action,next_action_payload=payload,evidence_type=etype,evidence_run_id=erun,evidence_summary=ev)
        before_supervised = str((item.metadata or {}).get("supervised_item_status", {}).get("status") or "")
        if request.dry_run or policy.policy_id == "supervised_item_status_dry_run_v1":
            status = "dry_run"
        else:
            status = "finalized" if to_status != "unchanged" else "unchanged"
            md = item.metadata or {}
            if request.update_item_status and policy.update_plan_item_status and hasattr(item, "status"):
                if policy.preserve_original_status and "original_status_before_supervised_finalize" not in md:
                    md["original_status_before_supervised_finalize"] = item.status
                item.status = to_status if to_status != "unchanged" else item.status
            if request.update_metadata:
                md["supervised_item_status"] = {"status": to_status, "finalize_run_id": finalize_id, "reason": reason, "next_action": next_action, "next_action_payload": payload, "evidence_type": etype, "evidence_run_id": erun, "updated_at": datetime.now(timezone.utc).isoformat()}
                hist = list(md.get("supervised_item_status_history") or [])
                hist.append({"finalize_run_id": finalize_id, "from_status": before_supervised, "to_status": to_status, "reason": reason, "next_action": next_action, "evidence_type": etype, "evidence_run_id": erun, "created_at": datetime.now(timezone.utc).isoformat()})
                md["supervised_item_status_history"] = hist[-policy.max_status_history:]
                item.metadata = md
            self.storage.save_pool(pool)
        res = AtlasSupervisedItemStatusFinalizeResult(pool_id=request.pool_id,item_id=request.item_id,run_id=rid,finalize_run_id=finalize_id,policy_id=policy.policy_id,status=status,item_status_before=str(item.status if status=="dry_run" else t.from_status),item_status_after=str(item.status),supervised_status_before=before_supervised,supervised_status_after=to_status,transition=t,selected_evidence={},evidence_index=ev,next_action=next_action,next_action_payload=payload,metadata={"side_effects":{"safe_apply_executed":False,"verification_executed":False,"bounded_retry_executed":False,"patch_regeneration_executed":False,"approval_executed":False,"rollback_executed":False,"restore_executed":False,"debug_review_executed":False}})
        self.save_result(res)
        self.emit(request.pool_id, rid, "supervised_item_status_result_saved", res)
        return res

    def collect_evidence(self, md: dict) -> dict:
        def last(key):
            vals = list(md.get(key) or [])
            return vals[-1] if vals else {}
        return {
            "latest_patch_candidate": last("patch_regen_candidates"),
            "latest_approval": last("patch_candidate_approvals"),
            "latest_handoff": last("safe_apply_handoffs"),
            "latest_safe_apply": last("supervised_handoff_safe_apply_results"),
            "latest_verification": last("supervised_handoff_verification_results"),
            "latest_retry": last("supervised_handoff_retry_results"),
            "latest_regen_recommendation": last("patch_regen_recommendations"),
            "latest_regen_from_recommendation": last("patch_regen_from_recommendation_results"),
        }

    def decide_transition(self, ev: dict):
        ver = ev.get("latest_verification") or {}; retry = ev.get("latest_retry") or {}; safe = ev.get("latest_safe_apply") or {}
        handoff = ev.get("latest_handoff") or {}; cand = ev.get("latest_patch_candidate") or {}; rec = ev.get("latest_regen_recommendation") or {}
        if str(ver.get("status") or "") == "failed_internal" or str(retry.get("status") or "") == "failed_internal": return "failed_internal", "latest_failed_internal", "investigate_failure", "verification", str(ver.get("verification_run_id") or "")
        if "blocked" in {str(ver.get("status") or ""), str(retry.get("status") or ""), str(rec.get("status") or "")} : return "blocked", "latest_blocked", "investigate_failure", "result", ""
        if ((ver.get("verification_status") or ver.get("status")) == "passed" and str(ver.get("evaluator_decision") or "").lower() in {"continue","passed","ok"}) or (str(retry.get("status") or "") == "recovered" and str(retry.get("final_verification_status") or "") == "passed"):
            return "completed", "verification_passed", "none", "verification", str(ver.get("verification_run_id") or retry.get("supervised_retry_run_id") or "")
        if str(cand.get("status") or "") == "proposal_ready" and cand.get("approval_status") == "pending":
            return "patch_candidate_ready", "candidate_pending_approval", "approve_patch_candidate", "patch_candidate", str(cand.get("regen_run_id") or "")
        if str(rec.get("status") or "") == "recommendation_ready":
            return "patch_regen_recommended", "recommendation_ready", "run_patch_regen_from_recommendation", "patch_regen_recommendation", str(rec.get("recommendation_run_id") or "")
        if str(handoff.get("safe_apply_ready") or "").lower() == "true" and not bool(handoff.get("safe_apply_executed")):
            return "safe_apply_ready", "handoff_ready", "run_supervised_safe_apply", "safe_apply_handoff", str(handoff.get("handoff_id") or "")
        if str(safe.get("status") or "") == "applied" and not ev.get("latest_verification"):
            return "verification_required", "safe_apply_done_verification_missing", "run_supervised_verification", "supervised_safe_apply", str(safe.get("safe_apply_execution_id") or "")
        if any(ev.values()):
            return "manual_required", "ambiguous_evidence", "manual_review", "mixed", ""
        return "unchanged", "no_useful_evidence", "manual_review", "none", ""

    def build_next_action_payload(self, request, ev, next_action):
        if next_action == "run_supervised_verification":
            return {"pool_id": request.pool_id, "item_id": request.item_id}
        return {"pool_id": request.pool_id, "item_id": request.item_id}

    def save_result(self, res):
        root = Path("ca_data") / "atlas" / "supervised_item_status" / res.pool_id
        root.mkdir(parents=True, exist_ok=True)
        (root / f"{res.finalize_run_id}.json").write_text(json.dumps(res.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        (root / f"{res.finalize_run_id}.md").write_text(f"# Supervised Item Status Finalization\n\n## Summary\n- finalize_run_id: {res.finalize_run_id}\n- pool_id: {res.pool_id}\n- item_id: {res.item_id}\n- status: {res.status}\n- next_action: {res.next_action}\n\n## Safety\n- safe_apply executed: false\n- verification executed: false\n- bounded retry executed: false\n- patch regeneration executed: false\n- approval executed: false\n- rollback/restore/debug executed: false\n", encoding="utf-8")

    def emit(self, pool_id, run_id, event_type, res):
        self.journal.append_event(pool_id, run_id, {"event_type": event_type, "finalize_run_id": res.finalize_run_id, "pool_id": res.pool_id, "item_id": res.item_id, "run_id": run_id, "status": res.status, "from_status": res.transition.from_status, "to_status": res.transition.to_status, "next_action": res.next_action, "evidence_type": res.transition.evidence_type, "evidence_run_id": res.transition.evidence_run_id, "safe_apply_executed": False, "verification_executed": False, "bounded_retry_executed": False, "patch_regeneration_executed": False, "approval_executed": False, "rollback_executed": False, "restore_executed": False, "debug_review_executed": False, "created_at": datetime.now(timezone.utc).isoformat()})
