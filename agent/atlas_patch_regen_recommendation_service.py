from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agent.atlas_dev_tool_path import validate_relative_path
from agent.atlas_journal import AtlasJournal
from agent.atlas_patch_regen_recommendation_policies import get_patch_regen_recommendation_policy
from agent.atlas_patch_regen_recommendation_schema import AtlasPatchRegenRecommendationRequest, AtlasPatchRegenRecommendationResult, AtlasPatchRegenRecommendedPayload
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage


class AtlasPatchRegenRecommendationService:
    def __init__(self, *, storage=None, journal=None):
        self.storage = storage or AtlasPlanPoolStorage(Path("ca_data"))
        self.journal = journal or AtlasJournal(Path("ca_data"))

    def recommend(self, request: AtlasPatchRegenRecommendationRequest) -> AtlasPatchRegenRecommendationResult:
        rec_id = f"regenrec_{uuid4().hex[:12]}"; rid = request.run_id or rec_id
        policy = get_patch_regen_recommendation_policy(request.policy_id)
        self.emit(request, rid, rec_id, "patch_regen_recommendation_started")
        retry = self._load("supervised_handoff_retry", request.pool_id, request.supervised_retry_run_id, "retryhandoff_")
        ver_id = str(retry.get("verification_run_id") or request.verification_run_id)
        safe_id = str(retry.get("safe_apply_execution_id") or request.safe_apply_execution_id)
        handoff_id = str(retry.get("handoff_id") or request.handoff_id)
        ver = self._load("supervised_handoff_verification", request.pool_id, ver_id, "verifyhandoff_")
        safe = self._load("supervised_handoff_safe_apply", request.pool_id, safe_id, "safehandoff_")
        handoff = self._load("safe_apply_handoffs", request.pool_id, handoff_id, "handoff_")
        pool = self.storage.load_pool(request.pool_id); item = pool.get_item(request.item_id)
        elig = self.assess(retry, ver, safe, handoff, item, policy)
        payload = None
        status = elig["status"]
        if elig["status"] == "recommendation_ready":
            payload = self.build_payload(request, rec_id, retry, ver, safe, handoff, item, elig)
            if request.dry_run: status = "dry_run"
        res = AtlasPatchRegenRecommendationResult(pool_id=request.pool_id,item_id=request.item_id,run_id=rid,handoff_id=handoff_id,safe_apply_execution_id=safe_id,verification_run_id=ver_id,supervised_retry_run_id=request.supervised_retry_run_id,recommendation_run_id=rec_id,policy_id=policy.policy_id,patch_regen_policy_id=request.patch_regen_policy_id,status=status,recommended_payload=payload,retry_result=retry,verification_result=ver,safe_apply_execution_result=safe,handoff=handoff,eligibility=elig,warnings=elig.get("warnings",[]),errors=elig.get("errors",[]),metadata={"side_effects":{"patch_regeneration_executed":False,"safe_apply_executed":False,"verification_executed":False,"bounded_retry_executed":False,"rollback_executed":False,"restore_executed":False,"debug_review_executed":False}})
        if not request.dry_run:
            self._update_metadata(pool, item, handoff, res)
            self.storage.save_pool(pool)
            self._write_handoff(request.pool_id, handoff_id, handoff)
        self._save(res)
        self.emit(request, rid, rec_id, f"patch_regen_recommendation_{status}", reason=elig.get("reason",""))
        self.emit(request, rid, rec_id, "patch_regen_recommendation_result_saved", reason=elig.get("reason",""))
        return res

    def assess(self, retry, ver, safe, handoff, item, policy):
        errs=[]; warns=[]
        if not retry: errs.append("retry_result_missing")
        if not ver: errs.append("verification_result_missing")
        if not safe: errs.append("safe_apply_result_missing")
        if item is None: errs.append("item_missing")
        rstatus=str(retry.get("status") or ""); vstatus=str((ver.get("verification_result") or {}).get("status") or ver.get("status") or "")
        reason=str((retry.get("retryability") or {}).get("reason") or "")
        target=list(handoff.get("target_files") or getattr(item,'target_files',[]) or (safe.get('target_files') or []))
        patch=str(handoff.get("patch") or ((safe.get("handoff") or {}).get("patch") or "") or ((getattr(item,'metadata',{}) or {}).get("patch") or ""))
        body=json.dumps({"retry":retry,"verification":ver},ensure_ascii=False).lower()
        det = bool((retry.get("retryability") or {}).get("deterministic_failure_detected")) or reason=="deterministic_test_failure_or_code_error" or any(x in body for x in ["assertionerror","syntaxerror","typeerror","nameerror","failed test","expected","actual","importerror","modulenotfounderror"])
        tr = "transient" in body or "environment" in body
        if safe.get("status")!="applied": errs.append("safe_apply_not_applied")
        if rstatus not in set(policy.eligible_retry_statuses): errs.append("retry_status_not_eligible")
        if vstatus not in set(policy.eligible_verification_statuses): errs.append("verification_status_not_failed")
        if not target: errs.append("target_files_missing")
        if len(target)>policy.max_target_files: errs.append("target_files_too_many")
        if not patch: errs.append("original_patch_missing")
        if not ((ver.get("failure_stop_suggestion") or retry.get("failure_stop_suggestion"))): errs.append("failure_evidence_missing")
        if errs: return {"eligible":False,"status":"blocked","reason":errs[0],"deterministic_failure_detected":det,"transient_failure_detected":tr,"evidence_sources":["retry_result","verification_result"],"warnings":warns,"errors":errs}
        if rstatus=="recovered" or vstatus=="passed" or (reason=="transient_or_environment_suspected" and rstatus!="exhausted"):
            return {"eligible":False,"status":"not_recommended","reason":"transient_or_recovered","deterministic_failure_detected":det,"transient_failure_detected":tr,"evidence_sources":["retryability"],"warnings":warns,"errors":[]}
        return {"eligible":True,"status":"recommendation_ready","reason":"eligible_retry_terminal_failure","deterministic_failure_detected":det,"transient_failure_detected":tr,"evidence_sources":["retryability","verification_logs"],"warnings":warns,"errors":[]}

    def build_payload(self, request, rec_id, retry, ver, safe, handoff, item, elig):
        return AtlasPatchRegenRecommendedPayload(pool_id=request.pool_id,item_id=request.item_id,run_id=request.run_id,workspace_id=request.workspace_id,project_path=request.project_path,policy_id=request.patch_regen_policy_id,context_bundle_id=str(ver.get("context_bundle_id") or (retry.get("bounded_retry_result") or {}).get("context_bundle_id") or handoff.get("context_bundle_id") or ""),retry_run_id=str(retry.get("bounded_retry_run_id") or ""),evaluator_result_id=str(ver.get("evaluator_result_id") or retry.get("evaluator_result_id") or handoff.get("evaluator_result_id") or ""),verification_result=ver.get("verification_result") or {},bounded_retry_result=retry.get("bounded_retry_result") or {},failure_stop_suggestion=ver.get("failure_stop_suggestion") or retry.get("failure_stop_suggestion") or {},original_patch=str(handoff.get("patch") or ((safe.get("handoff") or {}).get("patch") or "") or ((item.metadata or {}).get("patch") or "")),changed_files=list(ver.get("changed_files") or retry.get("changed_files") or safe.get("changed_files") or []),target_files=list(handoff.get("target_files") or item.target_files or safe.get("target_files") or []),metadata={"source":"patch_regen_recommendation","recommendation_run_id":rec_id,"supervised_retry_run_id":request.supervised_retry_run_id,"original_verification_run_id":str(ver.get('verification_run_id') or request.verification_run_id),"safe_apply_execution_id":str(safe.get('safe_apply_execution_id') or request.safe_apply_execution_id),"handoff_id":str(handoff.get('handoff_id') or request.handoff_id),"retry_status":str(retry.get('status') or ''),"retry_reason":str((retry.get('retryability') or {}).get('reason') or ''),"deterministic_failure_detected":elig.get("deterministic_failure_detected",False),"transient_failure_detected":elig.get("transient_failure_detected",False),"evidence_sources":elig.get("evidence_sources",[]),"auto_execute_patch_regen":False})

    def _update_metadata(self, pool, item, handoff, res):
        handoff.setdefault("metadata",{})
        handoff["metadata"].setdefault("patch_regen_recommendations",[]).append({"recommendation_run_id":res.recommendation_run_id,"supervised_retry_run_id":res.supervised_retry_run_id,"verification_run_id":res.verification_run_id,"status":res.status,"reason":res.eligibility.get("reason",""),"patch_regen_policy_id":res.patch_regen_policy_id,"created_at":res.created_at,"result_path":f"ca_data/atlas/patch_regen_recommendations/{res.pool_id}/{res.recommendation_run_id}.json","recommended_payload_path":f"ca_data/atlas/patch_regen_recommendations/{res.pool_id}/{res.recommendation_run_id}.json","auto_executed":False})
        handoff["metadata"].update({"last_patch_regen_recommendation_run_id":res.recommendation_run_id,"patch_regen_recommended":res.status=="recommendation_ready","patch_regen_reason":res.eligibility.get("reason",""),"recommended_regen_payload": {"target_files": (res.recommended_payload.target_files if res.recommended_payload else []), "changed_files": (res.recommended_payload.changed_files if res.recommended_payload else []), "policy_id":res.patch_regen_policy_id}})
        item.metadata = dict(item.metadata or {})
        item.metadata.setdefault("patch_regen_recommendations",[]).append({"recommendation_run_id":res.recommendation_run_id,"handoff_id":res.handoff_id,"safe_apply_execution_id":res.safe_apply_execution_id,"verification_run_id":res.verification_run_id,"supervised_retry_run_id":res.supervised_retry_run_id,"status":res.status,"reason":res.eligibility.get("reason",""),"patch_regen_policy_id":res.patch_regen_policy_id,"target_files":(res.recommended_payload.target_files if res.recommended_payload else []),"created_at":res.created_at,"result_path":f"ca_data/atlas/patch_regen_recommendations/{res.pool_id}/{res.recommendation_run_id}.json"})
        item.metadata["latest_patch_regen_recommendation_id"] = res.recommendation_run_id

    def _load(self, kind, pool_id, run_id, prefix):
        if prefix and not str(run_id).startswith(prefix): raise ValueError(f"invalid_id:{kind}")
        p = Path(self.storage.root_dir) / "atlas" / kind / validate_relative_path(pool_id) / f"{validate_relative_path(run_id)}.json"
        return json.loads(p.read_text(encoding="utf-8"))

    def _write_handoff(self, pool_id, handoff_id, handoff):
        p = Path(self.storage.root_dir) / "atlas" / "safe_apply_handoffs" / pool_id / f"{handoff_id}.json"
        p.write_text(json.dumps(handoff, ensure_ascii=False, indent=2), encoding="utf-8")

    def _save(self, res):
        d=Path(self.storage.root_dir)/"atlas"/"patch_regen_recommendations"/res.pool_id; d.mkdir(parents=True,exist_ok=True)
        (d/f"{res.recommendation_run_id}.json").write_text(json.dumps(res.model_dump(),ensure_ascii=False,indent=2),encoding="utf-8")
        (d/f"{res.recommendation_run_id}.md").write_text(f"# Patch Regen Recommendation\n\n## Summary\n- recommendation_run_id: {res.recommendation_run_id}\n- status: {res.status}\n\n## Safety\n- patch regeneration executed: false\n- safe_apply executed: false\n- verification executed: false\n- bounded retry executed: false\n",encoding="utf-8")

    def emit(self, req, rid, rec_id, event, **kw):
        self.journal.append_event(req.pool_id, rid, {"event_type":event,"recommendation_run_id":rec_id,"pool_id":req.pool_id,"item_id":req.item_id,"run_id":rid,"handoff_id":req.handoff_id,"safe_apply_execution_id":req.safe_apply_execution_id,"verification_run_id":req.verification_run_id,"supervised_retry_run_id":req.supervised_retry_run_id,"patch_regeneration_executed":False,"safe_apply_executed":False,"verification_executed":False,"bounded_retry_executed":False,"rollback_executed":False,"restore_executed":False,"debug_review_executed":False,"created_at":datetime.now(timezone.utc).isoformat(),**kw})
