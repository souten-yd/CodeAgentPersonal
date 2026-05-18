from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agent.atlas_auto_verification_schema import AtlasAutoVerificationRequest
from agent.atlas_auto_verification_service import AtlasAutoVerificationService
from agent.atlas_context_refresh_schema import AtlasContextRefreshRequest
from agent.atlas_context_refresh_service import AtlasContextRefreshService
from agent.atlas_dev_tool_path import validate_relative_path
from agent.atlas_failure_stop_service import AtlasFailureStopService
from agent.atlas_journal import AtlasJournal
from agent.atlas_llm_evaluator_schema import AtlasEvaluatorRequest
from agent.atlas_llm_evaluator_service import AtlasLLMEvaluatorService
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_supervised_handoff_verification_policies import get_supervised_handoff_verification_policy
from agent.atlas_supervised_handoff_verification_schema import AtlasSupervisedHandoffVerificationRequest, AtlasSupervisedHandoffVerificationResult
from agent.test_command_runner import TestCommandRunner


class AtlasSupervisedHandoffVerificationService:
    def __init__(self, *, storage=None, journal=None, verification_service=None, context_refresh_service=None, evaluator_service=None, failure_stop_service=None):
        self.storage = storage or AtlasPlanPoolStorage(Path("ca_data"))
        self.journal = journal or AtlasJournal(Path("ca_data"))
        self.verification_service = verification_service or AtlasAutoVerificationService(journal=self.journal, storage=self.storage, command_runner=TestCommandRunner())
        self.context_refresh_service = context_refresh_service or AtlasContextRefreshService()
        self.evaluator_service = evaluator_service or AtlasLLMEvaluatorService()
        self.failure_stop_service = failure_stop_service or AtlasFailureStopService()

    def run(self, request: AtlasSupervisedHandoffVerificationRequest) -> AtlasSupervisedHandoffVerificationResult:
        now = datetime.now(timezone.utc).isoformat(); vid=f"verifyhandoff_{uuid4().hex[:12]}"; rid=request.run_id or vid; policy=get_supervised_handoff_verification_policy(request.policy_id)
        safe=self._load_safe_apply(request.pool_id, request.safe_apply_execution_id); changed=list(safe.get("changed_files") or []); snap=str(safe.get("snapshot_id") or "")
        handoff,warning=self._load_handoff(request.pool_id, request.handoff_id or str(safe.get("handoff_id") or ""))
        warnings=[warning] if warning else []; errs=[]
        if safe.get("pool_id")!=request.pool_id or safe.get("item_id")!=request.item_id: errs.append("pool_item_mismatch")
        if safe.get("status")!="applied": errs.append("safe_apply_not_applied")
        se=((safe.get("metadata") or {}).get("side_effects") or {})
        if not se.get("safe_apply_executed", False) or se.get("verification_executed", False): errs.append("safe_apply_side_effects_invalid")
        if len(changed)>policy.max_changed_files: errs.append("changed_files_too_many")
        if handoff:
            if not handoff.get("safe_apply_executed", False): errs.append("handoff_safe_apply_not_executed")
            if policy.forbid_reverification and handoff.get("verification_executed", False): errs.append("handoff_already_verified")
        elif policy.require_handoff_safe_apply_executed:
            errs.append("handoff_missing")
        before={"safe_apply_executed":bool((handoff or {}).get("safe_apply_executed",False)),"verification_executed":bool((handoff or {}).get("verification_executed",False))}
        dry=request.dry_run or request.policy_id.endswith("dry_run_v1")
        if dry or errs:
            st="dry_run" if not errs else "blocked"
            return self._finish(request,vid,rid,policy.policy_id,st,{},safe,before,before,"","",{}, {},changed,snap,warnings,errs,{"would_verify":not bool(errs),"side_effects":self._side_effects(False)})
        context_bundle_id=""
        if request.include_context_refresh and policy.allow_context_refresh:
            ctx=self.context_refresh_service.refresh(AtlasContextRefreshRequest(pool_id=request.pool_id,item_id=request.item_id,run_id=rid,trigger="manual",workspace_id=request.workspace_id,project_path=request.project_path,changed_files=changed,policy_id=request.context_policy_id,include_local_tools=True,include_nexus_search=False,include_deep_research=False))
            context_bundle_id=ctx.bundle_id if hasattr(ctx,'bundle_id') else ""
        vr=self.verification_service.run_after_auto_safe_apply(AtlasAutoVerificationRequest(pool_id=request.pool_id,item_id=request.item_id,run_id=rid,workspace_id=request.workspace_id,metadata={"skip_safe_apply_check":True}))
        vrd=vr.model_dump(); vrd.setdefault("metadata",{}).update({"source":"supervised_handoff_safe_apply","handoff_id":(handoff or {}).get("handoff_id",request.handoff_id),"safe_apply_execution_id":request.safe_apply_execution_id,"snapshot_id":snap,"changed_files":changed})
        fs={}
        if vr.status=="failed":
            fs=self.failure_stop_service.build_for_verification_failure(pool_id=request.pool_id,item_id=request.item_id,verification_result=vrd,changed_files=changed,safe_apply_execution_id=request.safe_apply_execution_id,handoff_id=(handoff or {}).get("handoff_id",request.handoff_id),snapshot_id=snap).model_dump()
        eval_result_id=""; decision={}; status="passed" if vr.status=="passed" else vr.status
        if request.include_evaluator and policy.allow_evaluator:
            ev=self.evaluator_service.evaluate(AtlasEvaluatorRequest(pool_id=request.pool_id,item_id=request.item_id,run_id=rid,trigger="post_verification" if vr.status=="passed" else ("verification_failure" if vr.status=="failed" else "manual"),context_bundle_id=context_bundle_id,use_latest_context_bundle=False,project_path=request.project_path,changed_files=changed,verification_result=vrd,safe_apply_result=safe.get("safe_apply_result") or {},failure_stop_suggestion=fs,policy_id=request.evaluator_policy_id,metadata={"source":"supervised_handoff_verification","verification_run_id":vid,"safe_apply_execution_id":request.safe_apply_execution_id,"handoff_id":(handoff or {}).get("handoff_id",request.handoff_id),"snapshot_id":snap}))
            eval_result_id=str(((ev.model_dump()).get("metadata") or {}).get("evaluator_result_id") or "")
            decision=(ev.model_dump()).get("decision") or {}
            if decision.get("decision")=="manual_required": status="evaluator_manual_required"
            if decision.get("decision")=="stop": status="evaluator_stop"
        if vr.status=="failed" and status not in {"evaluator_stop","evaluator_manual_required"}: status="failed"
        if vr.status in {"blocked","skipped"}: status=vr.status
        return self._finish(request,vid,rid,policy.policy_id,status,vrd,safe,before,{"safe_apply_executed":True,"verification_executed":status not in {"blocked","dry_run"}},context_bundle_id,eval_result_id,decision,fs,changed,snap,warnings,[],{"side_effects":self._side_effects(status not in {"blocked","dry_run"})},handoff)

    def _load_safe_apply(self,pool_id,eid):
        p=Path(self.storage.root_dir)/"atlas"/"supervised_handoff_safe_apply"/validate_relative_path(pool_id)/f"{validate_relative_path(eid)}.json"
        return json.loads(p.read_text(encoding="utf-8"))

    def _load_handoff(self,pool_id,hid):
        if not hid: return None,"handoff_missing"
        p=Path(self.storage.root_dir)/"atlas"/"safe_apply_handoffs"/validate_relative_path(pool_id)/f"{validate_relative_path(hid)}.json"
        if not p.exists(): return None,"handoff_missing"
        return json.loads(p.read_text(encoding="utf-8")),""

    def _finish(self,req,vid,rid,policy_id,status,vr,safe,before,after,ctx,eid,dec,fs,changed,snap,warns,errs,meta,handoff=None):
        now=datetime.now(timezone.utc).isoformat()
        res=AtlasSupervisedHandoffVerificationResult(pool_id=req.pool_id,item_id=req.item_id,run_id=req.run_id,handoff_id=req.handoff_id or str((safe or {}).get("handoff_id") or ""),safe_apply_execution_id=req.safe_apply_execution_id,verification_run_id=vid,policy_id=policy_id,status=status,verification_result=vr,safe_apply_execution_result=safe,handoff_status_before=before,handoff_status_after=after,context_bundle_id=ctx,evaluator_result_id=eid,evaluator_decision=dec,failure_stop_suggestion=fs,changed_files=changed,snapshot_id=snap,warnings=warns,errors=errs,metadata=meta,created_at=now)
        d=Path(self.storage.root_dir)/"atlas"/"supervised_handoff_verification"/req.pool_id; d.mkdir(parents=True,exist_ok=True)
        jp=d/f"{vid}.json"; mp=d/f"{vid}.md"; jp.write_text(json.dumps(res.model_dump(),ensure_ascii=False,indent=2),encoding="utf-8")
        mp.write_text(f"# Supervised Handoff Verification\n\n## Summary\n- verification_run_id: {vid}\n- pool_id: {req.pool_id}\n- item_id: {req.item_id}\n- handoff_id: {res.handoff_id}\n- safe_apply_execution_id: {req.safe_apply_execution_id}\n- policy_id: {policy_id}\n- status: {status}\n\n## Safety\n- safe_apply rerun executed: false\n- bounded retry executed: false\n- rollback executed: false\n- restore executed: false\n- debug review executed: false\n- patch regeneration executed: false\n",encoding="utf-8")
        self.journal.append_event(req.pool_id, rid, {"event_type":f"supervised_handoff_verification_{status}","verification_run_id":vid,"pool_id":req.pool_id,"item_id":req.item_id,"run_id":rid,"handoff_id":res.handoff_id,"safe_apply_execution_id":req.safe_apply_execution_id,"policy_id":policy_id,"status":status,"verification_status":(vr or {}).get("status",""),"warning_count":len(warns),"error_count":len(errs)})
        return res

    def _side_effects(self, verification_executed: bool):
        return {"safe_apply_executed":True,"verification_executed":verification_executed,"bounded_retry_executed":False,"rollback_executed":False,"restore_executed":False,"debug_review_executed":False,"patch_regeneration_executed":False,"safe_apply_rerun_executed":False}
