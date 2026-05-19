from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from agent.atlas_dev_tool_path import validate_relative_path
from agent.atlas_multi_item_supervised_status_schema import AtlasMultiItemSupervisedStatusRequest, AtlasMultiItemSupervisedStatusResult
from agent.atlas_next_action_orchestrator_policies import get_next_action_orchestrator_policy
from agent.atlas_next_action_orchestrator_schema import AtlasNextActionContract, AtlasNextActionOrchestratorRequest, AtlasNextActionOrchestratorResult

ALLOW_PATHS = {
    "/api/atlas/patch-candidate-approval/decide": "AtlasPatchCandidateApprovalService.decide",
    "/api/atlas/supervised-handoff-safe-apply/execute": "AtlasSupervisedHandoffSafeApplyService.execute",
    "/api/atlas/supervised-handoff-verification/run": "AtlasSupervisedHandoffVerificationService.run",
    "/api/atlas/supervised-handoff-retry/run": "AtlasSupervisedHandoffRetryService.run",
    "/api/atlas/patch-regen-from-recommendation/run": "AtlasPatchRegenFromRecommendationService.run",
}

class AtlasNextActionOrchestratorService:
    def __init__(self, *, storage, journal, supervised_status_service):
        self.storage=storage; self.journal=journal; self.supervised_status_service=supervised_status_service

    def prepare(self, request: AtlasNextActionOrchestratorRequest) -> AtlasNextActionOrchestratorResult:
        pol = get_next_action_orchestrator_policy(request.policy_id)
        oid = f"nextaction_{uuid4().hex[:10]}"
        run_id = request.run_id or oid
        self.emit("next_action_orchestrator_started", request, oid)
        queue, qmeta, warns, errs = self.load_or_build_multi_status_queue(request)
        result = AtlasNextActionOrchestratorResult(pool_id=request.pool_id, run_id=run_id, orchestrator_run_id=oid, policy_id=pol.policy_id, status="blocked", multi_status_run_id=qmeta.get("multi_status_run_id", ""), warnings=warns, errors=errs, metadata={"queue_loaded_from": qmeta.get("queue_loaded_from", "")})
        if queue is None:
            self.save_result(result); self.emit("next_action_orchestrator_blocked", request, oid); return result
        summary = self.select_action_item(queue, request)
        if summary is None:
            result.status = "no_action"; self.save_result(result); return result
        self.emit("next_action_orchestrator_item_selected", request, oid, selected_item_id=summary.get("item_id", ""))
        c = self.map_next_action_to_contract(summary, request)
        self.emit("next_action_orchestrator_contract_built", request, oid, selected_next_action=c.next_action, action_kind=c.action_kind)
        self.validate_action_contract(c)
        self.emit("next_action_orchestrator_contract_validated", request, oid, payload_valid=c.payload_valid, missing_fields=c.missing_fields)
        result.selected_item_id = c.item_id; result.selected_next_action = c.next_action; result.action_contract = c
        result.queue_summary = {"counts": queue.counts, "next_item_id": (queue.next_item.item_id if queue.next_item else ""), "next_action": (queue.next_item.next_action if queue.next_item else "")}
        result.status = "manual_display" if c.action_kind == "manual_display" else ("action_ready" if c.payload_valid else "blocked")
        if request.dry_run or pol.policy_id == "next_action_orchestrator_dry_run_v1": result.status = "dry_run"
        self.save_result(result); self.emit("next_action_orchestrator_result_saved", request, oid, selected_item_id=result.selected_item_id, selected_next_action=result.selected_next_action)
        return result

    def load_or_build_multi_status_queue(self, request):
        root = Path("ca_data")/"atlas"/"multi_item_supervised_status"/request.pool_id
        warnings=[]; errors=[]; qmeta={"queue_loaded_from":"", "multi_status_run_id":""}
        if request.multi_status_run_id:
            if not request.multi_status_run_id.startswith("multistatus_"): return None, qmeta, warnings, ["invalid_multi_status_run_id"]
            p = root / f"{request.multi_status_run_id}.json"
            if p.exists():
                qmeta.update({"queue_loaded_from":"requested", "multi_status_run_id":request.multi_status_run_id})
                return AtlasMultiItemSupervisedStatusResult.model_validate(json.loads(p.read_text(encoding="utf-8"))), qmeta, warnings, errors
        files = sorted(root.glob("multistatus_*.json"), key=lambda x: x.stat().st_mtime, reverse=True) if root.exists() else []
        if files and not request.refresh_queue:
            data=json.loads(files[0].read_text(encoding="utf-8")); qmeta.update({"queue_loaded_from":"latest", "multi_status_run_id":data.get("multi_status_run_id","")}); return AtlasMultiItemSupervisedStatusResult.model_validate(data), qmeta, warnings, errors
        if not request.build_queue_if_missing and not request.refresh_queue: return None, qmeta, warnings, ["queue_not_found"]
        built = self.supervised_status_service.build_status(AtlasMultiItemSupervisedStatusRequest(pool_id=request.pool_id, run_id=request.run_id, workspace_id=request.workspace_id, project_path=request.project_path, policy_id=request.queue_policy_id, dry_run=True, refresh_item_status=False, update_item_status=False, update_metadata=False))
        qmeta.update({"queue_loaded_from":"built", "multi_status_run_id":built.multi_status_run_id})
        return built, qmeta, warnings, errors

    def select_action_item(self, queue, request):
        sums = queue.item_summaries or []
        if request.item_id and request.requested_next_action:
            for s in sums:
                if s.item_id == request.item_id and s.next_action == request.requested_next_action: return s.model_dump()
            return None
        if request.item_id:
            for s in sums:
                if s.item_id == request.item_id: return s.model_dump()
        if request.requested_next_action:
            for s in sorted(sums, key=lambda x: x.priority):
                if s.next_action == request.requested_next_action and s.selectable: return s.model_dump()
        if queue.next_item: return queue.next_item.model_dump()
        return sorted(sums, key=lambda x: x.priority)[0].model_dump() if sums else None

    def map_next_action_to_contract(self, s, request):
        n = s.get("next_action") or "none"; p = dict(s.get("next_action_payload") or {})
        base = dict(action_id=f"action_{uuid4().hex[:8]}", item_id=s.get("item_id",""), item_title=s.get("item_title",""), supervised_status=s.get("supervised_status",""), next_action=n, selectable=bool(s.get("selectable",False)), payload_valid=False, manual_required=(n!="none"), execution_allowed=False)
        m={
            "approve_patch_candidate":("execution_candidate","POST","/api/atlas/patch-candidate-approval/decide",["pool_id","item_id","regen_run_id","proposal_id"]),
            "run_supervised_safe_apply":("execution_candidate","POST","/api/atlas/supervised-handoff-safe-apply/execute",["pool_id","item_id","handoff_id"]),
            "run_supervised_verification":("execution_candidate","POST","/api/atlas/supervised-handoff-verification/run",["pool_id","item_id","safe_apply_execution_id"]),
            "run_supervised_retry":("execution_candidate","POST","/api/atlas/supervised-handoff-retry/run",["pool_id","item_id","verification_run_id","safe_apply_execution_id"]),
            "run_patch_regen_from_recommendation":("execution_candidate","POST","/api/atlas/patch-regen-from-recommendation/run",["pool_id","item_id","recommendation_run_id"]),
        }
        if n in {"manual_review","investigate_failure"}:
            payload={"pool_id":request.pool_id,"item_id":s.get("item_id",""),"reason":request.reason,"evidence_type":s.get("evidence_type",""),"evidence_run_id":s.get("evidence_run_id","")}
            return AtlasNextActionContract(**base, action_kind="manual_display", payload=payload, required_fields=["pool_id","item_id"])
        if n not in m: return AtlasNextActionContract(**base, action_kind="none", payload={"pool_id":request.pool_id,"item_id":s.get("item_id","")})
        kind, method, path, reqs = m[n]; payload={"pool_id":request.pool_id,"item_id":s.get("item_id",""), **p, "reviewer":request.reviewer, "reason":request.reason, "dry_run":False}
        if n=="approve_patch_candidate": payload.update({"decision_required":True,"suggested_decision":"approve"})
        return AtlasNextActionContract(**base, action_kind=kind, target_api_method=method, target_api_path=path, target_service=ALLOW_PATHS[path], payload=payload, required_fields=reqs)

    def validate_action_contract(self, c):
        miss=[k for k in c.required_fields if not c.payload.get(k)]; c.missing_fields=miss; c.payload_valid=(len(miss)==0)
        if c.target_api_path and c.target_api_path not in ALLOW_PATHS: c.errors.append("target_api_path_not_allowlisted")
        if c.action_kind=="manual_display" and c.target_api_path: c.errors.append("manual_display_must_not_have_target")
        if c.action_kind=="execution_candidate" and not c.selectable: c.errors.append("selected_item_unselectable")

    def save_result(self, r):
        root=Path("ca_data")/"atlas"/"next_action_orchestrator"/r.pool_id; root.mkdir(parents=True, exist_ok=True)
        (root/f"{r.orchestrator_run_id}.json").write_text(json.dumps(r.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        lines=["# Next Action Orchestrator","","## Summary",f"- orchestrator_run_id: {r.orchestrator_run_id}",f"- pool_id: {r.pool_id}",f"- status: {r.status}",f"- multi_status_run_id: {r.multi_status_run_id}",f"- selected_item_id: {r.selected_item_id}",f"- selected_next_action: {r.selected_next_action}","","## Safety","- next action executed: false","- safe_apply executed: false","- verification executed: false","- bounded retry executed: false","- patch regeneration executed: false","- approval executed: false","- rollback/restore/debug executed: false","- remote git executed: false"]
        (root/f"{r.orchestrator_run_id}.md").write_text("\n".join(lines)+"\n", encoding="utf-8")

    def emit(self, event_type, request, oid, **kw):
        self.journal.append_event(request.pool_id, request.run_id or oid, {"event_type":event_type,"orchestrator_run_id":oid,"pool_id":request.pool_id,"run_id":request.run_id or oid,"created_at":datetime.now(timezone.utc).isoformat(),"next_action_executed":False,"safe_apply_executed":False,"verification_executed":False,"bounded_retry_executed":False,"patch_regeneration_executed":False,"approval_executed":False,"rollback_executed":False,"restore_executed":False,"debug_review_executed":False,"remote_git_executed":False,**kw})
