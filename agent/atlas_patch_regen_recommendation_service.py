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
        try:
            retry = self._load("supervised_handoff_retry", request.pool_id, request.supervised_retry_run_id, "retryhandoff_")
            ver_id = str(retry.get("verification_run_id") or request.verification_run_id)
            safe_id = str(retry.get("safe_apply_execution_id") or request.safe_apply_execution_id)
            handoff_id = str(retry.get("handoff_id") or request.handoff_id)
            ver = self._load("supervised_handoff_verification", request.pool_id, ver_id, "verifyhandoff_")
            safe = self._load("supervised_handoff_safe_apply", request.pool_id, safe_id, "safehandoff_")
            handoff = self._load("safe_apply_handoffs", request.pool_id, handoff_id, "handoff_")
            pool = self.storage.load_pool(request.pool_id); item = pool.get_item(request.item_id)
            self.emit(request, rid, rec_id, "patch_regen_recommendation_input_loaded")
            elig = self.assess(retry, ver, safe, handoff, item, policy)
            self.emit(request, rid, rec_id, "patch_regen_recommendation_eligibility_assessed", **self._event_fields(elig, retry, ver))
            payload = None
            status = elig["status"]
            if elig["status"] == "recommendation_ready":
                payload = self.build_payload(request, rec_id, retry, ver, safe, handoff, item, elig, policy)
                self.emit(request, rid, rec_id, "patch_regen_recommendation_payload_built", **self._event_fields(elig, retry, ver, payload.target_files if payload else []))
                if request.dry_run:
                    status = "dry_run"
            res = AtlasPatchRegenRecommendationResult(pool_id=request.pool_id,item_id=request.item_id,run_id=rid,handoff_id=handoff_id,safe_apply_execution_id=safe_id,verification_run_id=ver_id,supervised_retry_run_id=request.supervised_retry_run_id,recommendation_run_id=rec_id,policy_id=policy.policy_id,patch_regen_policy_id=request.patch_regen_policy_id,status=status,recommended_payload=payload,retry_result=retry,verification_result=ver,safe_apply_execution_result=safe,handoff=handoff,eligibility=elig,warnings=elig.get("warnings",[]),errors=elig.get("errors",[]),metadata={"payload_chars":len(json.dumps((payload.model_dump() if payload else {}), ensure_ascii=False)),"payload_truncated":bool((payload and payload.metadata.get("payload_truncated"))),"payload_truncation_fields":list((payload.metadata.get("payload_truncation_fields", []) if payload else [])),"target_files_validated":bool(elig.get("target_files_validated",False)),"auto_execute_patch_regen":False,"recommended_next_api":{"endpoint":"/api/atlas/patch-regen/run","method":"POST","payload_source":"recommendation_result.recommended_payload"},"side_effects":self._side_effects()})
            if not request.dry_run:
                self._update_metadata(pool, item, handoff, res)
                self.storage.save_pool(pool)
                self._write_handoff(request.pool_id, handoff_id, handoff)
            self._save(res)
            self.emit(request, rid, rec_id, f"patch_regen_recommendation_{status}", **self._event_fields(elig, retry, ver, payload.target_files if payload else []))
            self.emit(request, rid, rec_id, "patch_regen_recommendation_result_saved", **self._event_fields(elig, retry, ver, payload.target_files if payload else []))
            return res
        except Exception as e:
            res = AtlasPatchRegenRecommendationResult(pool_id=request.pool_id,item_id=request.item_id,run_id=rid,handoff_id=request.handoff_id,safe_apply_execution_id=request.safe_apply_execution_id,verification_run_id=request.verification_run_id,supervised_retry_run_id=request.supervised_retry_run_id,recommendation_run_id=rec_id,policy_id=policy.policy_id,patch_regen_policy_id=request.patch_regen_policy_id,status="failed_internal",recommended_payload=None,eligibility={"status":"failed_internal","reason":"internal_error"},errors=["internal_error"],metadata={"side_effects":self._side_effects(),"auto_execute_patch_regen":False,"error_type":type(e).__name__})
            self.emit(request, rid, rec_id, "patch_regen_recommendation_failed_internal", status="failed_internal", reason="internal_error")
            try:
                self._save(res)
                self.emit(request, rid, rec_id, "patch_regen_recommendation_result_saved", status="failed_internal", reason="internal_error")
            except Exception:
                pass
            return res

    def assess(self, retry, ver, safe, handoff, item, policy):
        errs=[]; warns=[]
        retry = retry or {}
        ver = ver or {}
        safe = safe or {}
        handoff = handoff or {}
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
        tr = any(x in body for x in ["timeout","timed out","runner unavailable","connection refused","connection reset","temporary failure","transient","environment","infrastructure","flaky","resource temporarily unavailable"])
        target_valid = True
        for p in target:
            if not str(p).strip() or str(p) == "/dev/null":
                target_valid = False
            elif str(p).startswith("/") or ".." in str(p):
                target_valid = False
            else:
                validate_relative_path(str(p))
        if safe.get("status")!="applied": errs.append("safe_apply_not_applied")
        if rstatus not in ("exhausted","not_retryable","stopped","recovered"): errs.append("retry_status_unknown")
        if vstatus not in set(policy.eligible_verification_statuses + ["passed"]): errs.append("verification_status_unknown")
        if not target: errs.append("target_files_missing")
        if not target_valid: errs.append("target_files_invalid")
        if len(target)>policy.max_target_files: errs.append("target_files_too_many")
        if not patch: errs.append("original_patch_missing")
        if not ((ver.get("failure_stop_suggestion") or retry.get("failure_stop_suggestion"))): errs.append("failure_evidence_missing")

        def eligibility(eligible, status, display_reason, target_files_validated, evidence_sources, errors=None):
            return {"eligible":eligible,"status":status,"reason":display_reason,"retry_status":rstatus,"verification_status":vstatus,"retry_reason":reason,"target_files":target,"target_files_validated":target_files_validated,"deterministic_failure_detected":det,"transient_failure_detected":tr,"evidence_sources":evidence_sources,"warnings":warns,"errors":errors if errors is not None else []}

        if errs:
            return eligibility(False,"blocked",errs[0],False,["retry_result","verification_result"],errs)
        if rstatus=="recovered" or vstatus=="passed":
            return eligibility(False,"not_recommended","transient_or_recovered",True,["retryability"])
        if rstatus=="not_retryable" and not det:
            return eligibility(False,"not_recommended","not_retryable_without_deterministic_evidence",True,["retryability"])
        if rstatus=="stopped" and not (det or "evaluator_stop" in body):
            return eligibility(False,"not_recommended","stopped_without_evidence",True,["retryability"])
        if tr and not det and rstatus != "exhausted":
            return eligibility(False,"not_recommended","transient_or_recovered",True,["retryability"])
        return eligibility(True,"recommendation_ready","eligible_retry_terminal_failure",True,["retryability","verification_logs"])

    def build_payload(self, request, rec_id, retry, ver, safe, handoff, item, elig, policy):
        original_patch=str(handoff.get("patch") or ((safe.get("handoff") or {}).get("patch") or "") or ((item.metadata or {}).get("patch") or ""))
        target_files=list(handoff.get("target_files") or item.target_files or safe.get("target_files") or [])
        for p in target_files: validate_relative_path(str(p))
        payload = AtlasPatchRegenRecommendedPayload(pool_id=request.pool_id,item_id=request.item_id,run_id=request.run_id,workspace_id=request.workspace_id,project_path=request.project_path,policy_id=request.patch_regen_policy_id,context_bundle_id=str(ver.get("context_bundle_id") or (retry.get("bounded_retry_result") or {}).get("context_bundle_id") or handoff.get("context_bundle_id") or ""),retry_run_id=str(retry.get("bounded_retry_run_id") or ""),evaluator_result_id=str(ver.get("evaluator_result_id") or retry.get("evaluator_result_id") or handoff.get("evaluator_result_id") or ""),verification_result=ver.get("verification_result") or {},bounded_retry_result=retry.get("bounded_retry_result") or {},failure_stop_suggestion=ver.get("failure_stop_suggestion") or retry.get("failure_stop_suggestion") or {},original_patch=original_patch,changed_files=list(ver.get("changed_files") or retry.get("changed_files") or safe.get("changed_files") or []),target_files=target_files,metadata={"source":"patch_regen_recommendation","recommendation_run_id":rec_id,"supervised_retry_run_id":request.supervised_retry_run_id,"original_verification_run_id":str(ver.get('verification_run_id') or request.verification_run_id),"safe_apply_execution_id":str(safe.get('safe_apply_execution_id') or request.safe_apply_execution_id),"handoff_id":str(handoff.get('handoff_id') or request.handoff_id),"retry_status":str(retry.get('status') or ''),"retry_reason":str((retry.get('retryability') or {}).get('reason') or ''),"deterministic_failure_detected":elig.get("deterministic_failure_detected",False),"transient_failure_detected":elig.get("transient_failure_detected",False),"evidence_sources":elig.get("evidence_sources",[]),"payload_truncated":False,"payload_chars":0,"payload_truncation_fields":[],"auto_execute_patch_regen":False})
        body = json.dumps(payload.model_dump(), ensure_ascii=False)
        if len(body) > policy.max_payload_chars:
            payload.bounded_retry_result = {"truncated": True}
            payload.metadata["payload_truncated"] = True
            payload.metadata["payload_truncation_fields"] = ["bounded_retry_result"]
        payload.metadata["payload_chars"] = len(json.dumps(payload.model_dump(), ensure_ascii=False))
        return payload

    def _side_effects(self):
        return {"patch_regeneration_executed":False,"safe_apply_executed":False,"verification_executed":False,"bounded_retry_executed":False,"rollback_executed":False,"restore_executed":False,"debug_review_executed":False}

    def _event_fields(self, elig, retry, ver, target_files=None):
        return {"status":elig.get("status",""),"reason":elig.get("reason",""),"retry_status":str(elig.get("retry_status") or (retry or {}).get("status") or ""),"verification_status":str(elig.get("verification_status") or ((ver or {}).get("verification_result") or {}).get("status") or (ver or {}).get("status") or ""),"deterministic_failure_detected":bool(elig.get("deterministic_failure_detected",False)),"transient_failure_detected":bool(elig.get("transient_failure_detected",False)),"target_files":target_files or elig.get("target_files") or [],**self._side_effects()}

    def _update_metadata(self, pool, item, handoff, res):
        target_files = res.recommended_payload.target_files if res.recommended_payload else []
        result_path = f"ca_data/atlas/patch_regen_recommendations/{res.pool_id}/{res.recommendation_run_id}.json"
        recommendation_entry = {"recommendation_run_id":res.recommendation_run_id,"handoff_id":res.handoff_id,"safe_apply_execution_id":res.safe_apply_execution_id,"verification_run_id":res.verification_run_id,"supervised_retry_run_id":res.supervised_retry_run_id,"status":res.status,"reason":res.eligibility.get("reason",""),"patch_regen_policy_id":res.patch_regen_policy_id,"target_files":target_files,"created_at":res.created_at,"result_path":result_path}

        handoff.setdefault("metadata",{})
        handoff["metadata"].setdefault("patch_regen_recommendations",[]).append({**recommendation_entry,"recommended_payload_path":result_path,"auto_executed":False})
        handoff["metadata"].update({"last_patch_regen_recommendation_run_id":res.recommendation_run_id,"patch_regen_recommended":res.status=="recommendation_ready","patch_regen_reason":res.eligibility.get("reason",""),"recommended_regen_payload": {"target_files": target_files, "changed_files": (res.recommended_payload.changed_files if res.recommended_payload else []), "policy_id":res.patch_regen_policy_id}})

        item.metadata = dict(item.metadata or {})
        item.metadata.setdefault("patch_regen_recommendations", []).append(recommendation_entry)
        item.metadata["latest_patch_regen_recommendation_id"] = res.recommendation_run_id
        safe_apply_handoffs = item.metadata.get("safe_apply_handoffs")
        if isinstance(safe_apply_handoffs, list):
            for safe_apply_handoff in safe_apply_handoffs:
                if isinstance(safe_apply_handoff, dict) and safe_apply_handoff.get("handoff_id") == res.handoff_id:
                    safe_apply_handoff["patch_regen_recommended"] = res.status == "recommendation_ready"
                    safe_apply_handoff["patch_regen_reason"] = res.eligibility.get("reason", "")
                    safe_apply_handoff["last_patch_regen_recommendation_id"] = res.recommendation_run_id

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
        md = f"# Patch Regen Recommendation\n\n## Summary\n- recommendation_run_id: {res.recommendation_run_id}\n- pool_id: {res.pool_id}\n- item_id: {res.item_id}\n- handoff_id: {res.handoff_id}\n- safe_apply_execution_id: {res.safe_apply_execution_id}\n- verification_run_id: {res.verification_run_id}\n- supervised_retry_run_id: {res.supervised_retry_run_id}\n- status: {res.status}\n- reason: {res.eligibility.get('reason','')}\n- patch_regen_policy_id: {res.patch_regen_policy_id}\n\n## Eligibility\n- retry_status: {res.eligibility.get('retry_status','')}\n- verification_status: {res.eligibility.get('verification_status','')}\n- retry_reason: {res.eligibility.get('retry_reason','')}\n- deterministic_failure_detected: {res.eligibility.get('deterministic_failure_detected',False)}\n- transient_failure_detected: {res.eligibility.get('transient_failure_detected',False)}\n- evidence_sources: {res.eligibility.get('evidence_sources',[])}\n- target_files: {res.eligibility.get('target_files', [])}\n\n## Recommended Payload Preview\n- target_files: {(res.recommended_payload.target_files if res.recommended_payload else res.eligibility.get('target_files', []))}\n- changed_files: {(res.recommended_payload.changed_files if res.recommended_payload else [])}\n- context_bundle_id: {(res.recommended_payload.context_bundle_id if res.recommended_payload else '')}\n- retry_run_id: {(res.recommended_payload.retry_run_id if res.recommended_payload else '')}\n- evaluator_result_id: {(res.recommended_payload.evaluator_result_id if res.recommended_payload else '')}\n- failure_stop_suggestion summary: {bool((res.recommended_payload.failure_stop_suggestion if res.recommended_payload else {}))}\n- original_patch_chars: {len((res.recommended_payload.original_patch if res.recommended_payload else ''))}\n\n## Safety\n- patch regeneration executed: false\n- safe_apply executed: false\n- verification executed: false\n- bounded retry executed: false\n- rollback/restore/debug executed: false\n"
        (d/f"{res.recommendation_run_id}.md").write_text(md,encoding="utf-8")

    def emit(self, req, rid, rec_id, event, **kw):
        self.journal.append_event(req.pool_id, rid, {"event_type":event,"recommendation_run_id":rec_id,"pool_id":req.pool_id,"item_id":req.item_id,"run_id":rid,"handoff_id":req.handoff_id,"safe_apply_execution_id":req.safe_apply_execution_id,"verification_run_id":req.verification_run_id,"supervised_retry_run_id":req.supervised_retry_run_id,**self._side_effects(),"created_at":datetime.now(timezone.utc).isoformat(),**kw})
