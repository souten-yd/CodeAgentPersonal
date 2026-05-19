from __future__ import annotations
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from uuid import uuid4
from agent.atlas_dev_tool_path import validate_relative_path
from agent.atlas_manual_next_action_executor_policies import get_manual_next_action_executor_policy
from agent.atlas_manual_next_action_executor_schema import AtlasManualNextActionExecutorRequest, AtlasManualNextActionExecutionResult
from agent.atlas_patch_candidate_approval_schema import AtlasPatchCandidateApprovalRequest
from agent.atlas_supervised_handoff_safe_apply_schema import AtlasSupervisedHandoffSafeApplyRequest
from agent.atlas_supervised_handoff_verification_schema import AtlasSupervisedHandoffVerificationRequest
from agent.atlas_supervised_handoff_retry_schema import AtlasSupervisedHandoffRetryRequest
from agent.atlas_patch_regen_from_recommendation_schema import AtlasPatchRegenFromRecommendationRequest

ALLOW = {
"approve_patch_candidate":"AtlasPatchCandidateApprovalService.decide",
"run_supervised_safe_apply":"AtlasSupervisedHandoffSafeApplyService.execute",
"run_supervised_verification":"AtlasSupervisedHandoffVerificationService.run",
"run_supervised_retry":"AtlasSupervisedHandoffRetryService.run",
"run_patch_regen_from_recommendation":"AtlasPatchRegenFromRecommendationService.run",
}

class AtlasManualNextActionExecutorService:
    def __init__(self, *, storage, journal, approval_service, safe_apply_service, verification_service, retry_service, patch_regen_service):
        self.storage=storage; self.journal=journal; self.approval_service=approval_service; self.safe_apply_service=safe_apply_service; self.verification_service=verification_service; self.retry_service=retry_service; self.patch_regen_service=patch_regen_service

    def execute(self, request: AtlasManualNextActionExecutorRequest) -> AtlasManualNextActionExecutionResult:
        exid=f"manualexec_{uuid4().hex[:10]}"; rid=request.run_id or exid; pol=get_manual_next_action_executor_policy(request.policy_id)
        r=AtlasManualNextActionExecutionResult(pool_id=request.pool_id,run_id=rid,executor_run_id=exid,orchestrator_run_id=request.orchestrator_run_id,policy_id=pol.policy_id,status="blocked")
        self._emit(request,r,"manual_next_action_executor_started")
        try:
            orb=self._load_orchestrator(request,r); c=dict(orb.get("action_contract") or {})
            r.orchestrator_result=orb; r.action_contract=c; r.selected_item_id=str(c.get("item_id") or ""); r.selected_next_action=str(c.get("next_action") or ""); r.action_id=str(c.get("action_id") or ""); r.action_kind=str(c.get("action_kind") or ""); r.target_service=str(c.get("target_service") or ""); r.target_api_path=str(c.get("target_api_path") or "")
            errs=[]
            if orb.get("status")!="action_ready": errs.append("orchestrator_status_not_action_ready")
            if c.get("manual_required") is not True: errs.append("manual_required_false")
            if c.get("execution_allowed") is not False: errs.append("execution_allowed_must_be_false")
            if c.get("action_kind")!="execution_candidate": errs.append("manual_display_not_executable")
            if request.expected_next_action and request.expected_next_action!=r.selected_next_action: errs.append("expected_next_action_mismatch")
            if request.action_id and request.action_id!=r.action_id: errs.append("action_id_mismatch")
            if r.selected_next_action not in ALLOW or r.target_service!=ALLOW.get(r.selected_next_action): errs.append("target_service_not_allowlisted")
            if c.get("payload_valid") is not True or c.get("missing_fields"): errs.append("payload_invalid")
            token=f"MANUAL_EXECUTE:{request.orchestrator_run_id}:{r.action_id}:{r.selected_next_action}:{r.selected_item_id}"
            confirm_ok=(request.confirmation_token==token and (request.confirmation_text or "").strip()=="EXECUTE ONE ACTION")
            if not request.dry_run and not confirm_ok: errs.append("confirmation_required")
            if not request.dry_run and pol.require_dry_run_before_execute and request.require_dry_run_first and not self._has_prior_dryrun(request,r): errs.append("dry_run_required_before_execute")
            r.validation={"executable":len(errs)==0,"confirmation_valid":confirm_ok,"dry_run_first_satisfied":"dry_run_required_before_execute" not in errs}
            if errs:
                r.errors.extend(errs); r.status="dry_run" if request.dry_run else "blocked"; self._emit(request,r,"manual_next_action_executor_blocked"); return self._save(request,r)
            if request.dry_run or pol.policy_id=="manual_next_action_executor_dry_run_v1":
                r.status="dry_run"; self._emit(request,r,"manual_next_action_executor_dry_run"); return self._save(request,r)
            payload=dict(c.get("payload") or {})
            self._emit(request,r,"manual_next_action_executor_service_started")
            exec_result=self._call(request,r,payload)
            r.execution_result=exec_result; r.execution_result_id=str(exec_result.get("approval_run_id") or exec_result.get("execution_id") or exec_result.get("verification_run_id") or exec_result.get("supervised_retry_run_id") or exec_result.get("recommendation_exec_id") or "")
            r.status="executed"; self._emit(request,r,"manual_next_action_executor_service_completed"); self._emit(request,r,"manual_next_action_executor_executed")
            return self._save(request,r,update_metadata=True)
        except Exception as exc:
            r.status="failed_internal"; r.errors.append(f"unexpected_executor_exception:{exc.__class__.__name__}"); self._emit(request,r,"manual_next_action_executor_failed_internal"); return self._save(request,r)

    def _load_orchestrator(self, req, r):
        if not req.orchestrator_run_id.startswith("nextaction_"): raise ValueError("invalid_orchestrator_run_id")
        p=Path("ca_data")/"atlas"/"next_action_orchestrator"/validate_relative_path(req.pool_id)/f"{validate_relative_path(req.orchestrator_run_id)}.json"
        if not p.exists(): raise FileNotFoundError("orchestrator_result_not_found")
        data=json.loads(p.read_text(encoding="utf-8")); self._emit(req,r,"manual_next_action_executor_orchestrator_loaded"); return data
    def _has_prior_dryrun(self, req, r):
        root=Path("ca_data")/"atlas"/"manual_next_action_executor"/validate_relative_path(req.pool_id)
        if not root.exists(): return False
        now=datetime.now(timezone.utc)
        for p in sorted(root.glob("manualexec_*.json"), key=lambda x:x.stat().st_mtime, reverse=True):
            d=json.loads(p.read_text(encoding="utf-8"));
            if d.get("status")=="dry_run" and (d.get("validation") or {}).get("executable") is True and d.get("orchestrator_run_id")==req.orchestrator_run_id and d.get("action_id")==r.action_id and d.get("selected_next_action")==r.selected_next_action:
                ts=datetime.fromisoformat(d.get("created_at"));
                if now-ts<=timedelta(hours=24): return True
        return False
    def _call(self, req, r, p):
        m={"source":"manual_next_action_executor","executor_run_id":r.executor_run_id,"orchestrator_run_id":req.orchestrator_run_id,"action_id":r.action_id,**dict(req.metadata or {})}
        if r.selected_next_action=="approve_patch_candidate":
            return self.approval_service.decide(AtlasPatchCandidateApprovalRequest(pool_id=p["pool_id"],item_id=p["item_id"],run_id=req.run_id,workspace_id=req.workspace_id,regen_run_id=p["regen_run_id"],proposal_id=p.get("proposal_id","") ,decision=req.explicit_decision,reviewer=req.reviewer,reason=req.reason,metadata={**m,"manual_confirmation":True})).model_dump()
        if r.selected_next_action=="run_supervised_safe_apply":
            return self.safe_apply_service.execute(AtlasSupervisedHandoffSafeApplyRequest(pool_id=p["pool_id"],item_id=p["item_id"],run_id=req.run_id,workspace_id=req.workspace_id,handoff_id=p["handoff_id"],dry_run=req.dry_run,reviewer=req.reviewer,reason=req.reason,metadata=m)).model_dump()
        if r.selected_next_action=="run_supervised_verification":
            return self.verification_service.run(AtlasSupervisedHandoffVerificationRequest(pool_id=p["pool_id"],item_id=p["item_id"],run_id=req.run_id,workspace_id=req.workspace_id,safe_apply_execution_id=p["safe_apply_execution_id"],handoff_id=p.get("handoff_id","") ,dry_run=req.dry_run,reviewer=req.reviewer,reason=req.reason,metadata=m)).model_dump()
        if r.selected_next_action=="run_supervised_retry":
            return self.retry_service.run(AtlasSupervisedHandoffRetryRequest(pool_id=p["pool_id"],item_id=p["item_id"],run_id=req.run_id,workspace_id=req.workspace_id,verification_run_id=p["verification_run_id"],safe_apply_execution_id=p["safe_apply_execution_id"],handoff_id=p.get("handoff_id","") ,dry_run=req.dry_run,reviewer=req.reviewer,reason=req.reason,metadata=m)).model_dump()
        return self.patch_regen_service.run(AtlasPatchRegenFromRecommendationRequest(pool_id=p["pool_id"],item_id=p["item_id"],run_id=req.run_id,workspace_id=req.workspace_id,recommendation_run_id=p["recommendation_run_id"],dry_run=req.dry_run,reviewer=req.reviewer,reason=req.reason,metadata=m)).model_dump()
    def _save(self, req, r, update_metadata=False):
        root=Path("ca_data")/"atlas"/"manual_next_action_executor"/req.pool_id; root.mkdir(parents=True, exist_ok=True)
        (root/f"{r.executor_run_id}.json").write_text(json.dumps(r.model_dump(),ensure_ascii=False,indent=2),encoding="utf-8")
        (root/f"{r.executor_run_id}.md").write_text(f"# Manual Next Action Executor\n\n## Summary\n- executor_run_id: {r.executor_run_id}\n- orchestrator_run_id: {r.orchestrator_run_id}\n- pool_id: {r.pool_id}\n- status: {r.status}\n",encoding="utf-8")
        if update_metadata:
            pool=self.storage.load_pool(req.pool_id); item=pool.get_item(r.selected_item_id)
            if item:
                md=item.metadata or {}; rows=list(md.get("manual_next_action_executions") or [])
                rows.append({"executor_run_id":r.executor_run_id,"orchestrator_run_id":r.orchestrator_run_id,"action_id":r.action_id,"next_action":r.selected_next_action,"status":r.status,"dry_run":req.dry_run,"execution_result_id":r.execution_result_id,"created_at":r.created_at,"result_path":f"ca_data/atlas/manual_next_action_executor/{r.pool_id}/{r.executor_run_id}.json"})
                md["manual_next_action_executions"]=rows; md["latest_manual_next_action_executor_run_id"]=r.executor_run_id; item.metadata=md; self.storage.save_pool(pool); self.journal.save_plan_pool(pool)
        self._emit(req,r,"manual_next_action_executor_result_saved"); return r
    def _emit(self, req, r, event):
        self.journal.append_event(req.pool_id, req.run_id or r.executor_run_id,{"event_type":event,"executor_run_id":r.executor_run_id,"orchestrator_run_id":req.orchestrator_run_id,"pool_id":req.pool_id,"run_id":req.run_id or r.executor_run_id,"selected_item_id":r.selected_item_id,"selected_next_action":r.selected_next_action,"action_id":r.action_id,"target_service":r.target_service,"target_api_path":r.target_api_path,"status":r.status,"dry_run":req.dry_run,"execution_result_id":r.execution_result_id,"one_action_executed":r.status=="executed","next_action_executed":r.status=="executed","auto_continue_executed":False,"multi_item_autopilot_continued":False,"rollback_executed":False,"restore_executed":False,"debug_review_executed":False,"remote_git_executed":False,"created_at":datetime.now(timezone.utc).isoformat()})
