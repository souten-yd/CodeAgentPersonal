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
        self.failure_stop_service = failure_stop_service or AtlasFailureStopService(journal=self.journal)

    def run(self, request: AtlasSupervisedHandoffVerificationRequest) -> AtlasSupervisedHandoffVerificationResult:
        vid = f"verifyhandoff_{uuid4().hex[:12]}"; rid = request.run_id or vid; policy = get_supervised_handoff_verification_policy(request.policy_id)
        side = self._side_effects(False)
        self._emit(request, rid, "supervised_handoff_verification_started", vid, side)
        safe = self._load_safe_apply(request.pool_id, request.safe_apply_execution_id); changed = list(safe.get("changed_files") or []); snap = str(safe.get("snapshot_id") or "")
        handoff, warning = self._load_handoff(request.pool_id, request.handoff_id or str(safe.get("handoff_id") or ""))
        self._emit(request, rid, "supervised_handoff_verification_input_loaded", vid, side)
        warnings = [warning] if warning else []; errs = []; vrd = {}; fs = {}; dec = {}; eval_result_id = ""; ctx = ""; ctx_status = "skipped"; val_errors = []
        if safe.get("pool_id") != request.pool_id or safe.get("item_id") != request.item_id: errs.append("pool_item_mismatch")
        if safe.get("status") != "applied": errs.append("safe_apply_not_applied")
        se = ((safe.get("metadata") or {}).get("side_effects") or {})
        if not se.get("safe_apply_executed", False) or se.get("verification_executed", False): errs.append("safe_apply_side_effects_invalid")
        if len(changed) > policy.max_changed_files: errs.append("changed_files_too_many")
        if handoff:
            if not handoff.get("safe_apply_executed", False): errs.append("handoff_safe_apply_not_executed")
            if policy.forbid_reverification and handoff.get("verification_executed", False): errs.append("handoff_already_verified")
        elif policy.require_handoff_safe_apply_executed:
            errs.append("handoff_missing")
        val_errors = list(errs)
        self._emit(request, rid, "supervised_handoff_verification_validation_completed", vid, side, {"validation_errors": val_errors})
        dry = request.dry_run or request.policy_id.endswith("dry_run_v1")
        before = {"safe_apply_executed": bool((handoff or {}).get("safe_apply_executed", False)), "verification_executed": bool((handoff or {}).get("verification_executed", False))}
        status = "dry_run" if dry and not errs else ("blocked" if errs else "")
        verification_attempted = False; evaluator_attempted = False

        if not status:
            if request.include_context_refresh and policy.allow_context_refresh:
                self._emit(request, rid, "supervised_handoff_context_refresh_started", vid, side)
                try:
                    c = self.context_refresh_service.refresh(AtlasContextRefreshRequest(pool_id=request.pool_id, item_id=request.item_id, run_id=rid, trigger="manual", workspace_id=request.workspace_id, project_path=request.project_path, changed_files=changed, policy_id=request.context_policy_id, include_local_tools=True, include_nexus_search=False, include_deep_research=False))
                    ctx = c.bundle_id if hasattr(c, "bundle_id") else ""; ctx_status = "completed"
                except Exception as exc:
                    warnings.append(f"context_refresh_exception:{type(exc).__name__}"); ctx = ""; ctx_status = "failed"
                self._emit(request, rid, "supervised_handoff_context_refresh_completed", vid, side, {"context_refresh_status": ctx_status})
            try:
                self._emit(request, rid, "supervised_handoff_verification_runner_started", vid, side)
                vr = self.verification_service.run_after_auto_safe_apply(AtlasAutoVerificationRequest(pool_id=request.pool_id, item_id=request.item_id, run_id=rid, workspace_id=request.workspace_id, metadata={"source": "supervised_handoff_verification", "safe_apply_execution_id": request.safe_apply_execution_id, "handoff_id": (handoff or {}).get("handoff_id", request.handoff_id), "changed_files": changed, "snapshot_id": snap, "skip_safe_apply_check": True}))
                verification_attempted = True
                vrd = vr.model_dump(); vrd.setdefault("metadata", {}).update({"source": "supervised_handoff_verification", "handoff_id": (handoff or {}).get("handoff_id", request.handoff_id), "safe_apply_execution_id": request.safe_apply_execution_id, "snapshot_id": snap, "changed_files": changed})
                self._emit(request, rid, "supervised_handoff_verification_runner_completed", vid, side, {"verification_status": vr.status})
            except Exception as exc:
                status = "failed_internal"; warnings.append(f"verification_exception:{type(exc).__name__}"); vrd = {"status": "failed_internal", "errors": [f"verification_exception:{type(exc).__name__}"]}

            if vrd.get("status") == "failed":
                fs = self.failure_stop_service.build_for_verification_failure(pool_id=request.pool_id, item_id=request.item_id, verification_result=vrd, changed_files=changed, safe_apply_execution_id=request.safe_apply_execution_id, handoff_id=(handoff or {}).get("handoff_id", request.handoff_id), snapshot_id=snap).model_dump()

            if status != "failed_internal" and request.include_evaluator and policy.allow_evaluator:
                try:
                    evaluator_attempted = True
                    self._emit(request, rid, "supervised_handoff_evaluator_started", vid, side)
                    ev = self.evaluator_service.evaluate(AtlasEvaluatorRequest(pool_id=request.pool_id, item_id=request.item_id, run_id=rid, trigger="post_verification", context_bundle_id=ctx, use_latest_context_bundle=False, project_path=request.project_path, changed_files=changed, verification_result=vrd, safe_apply_result=safe.get("safe_apply_result") or {}, failure_stop_suggestion=fs, policy_id=request.evaluator_policy_id, metadata={"source": "supervised_handoff_verification", "verification_run_id": vid, "safe_apply_execution_id": request.safe_apply_execution_id, "handoff_id": (handoff or {}).get("handoff_id", request.handoff_id), "snapshot_id": snap}))
                    eval_result_id = str(((ev.model_dump()).get("metadata") or {}).get("evaluator_result_id") or "")
                    dec = (ev.model_dump()).get("decision") or {}
                    self._emit(request, rid, "supervised_handoff_evaluator_completed", vid, side)
                except Exception as exc:
                    warnings.append(f"evaluator_exception:{type(exc).__name__}")

            if status != "failed_internal":
                vr_status = vrd.get("status", "skipped")
                status = "passed" if vr_status == "passed" else ("failed" if vr_status == "failed" else vr_status)

        verification_executed = (vrd.get("status") in {"passed", "failed"}) if vrd else False
        side = self._side_effects(verification_executed)
        if status == "failed": self._emit(request, rid, "supervised_handoff_verification_failed", vid, side)
        elif status == "passed": self._emit(request, rid, "supervised_handoff_verification_passed", vid, side)
        elif status == "blocked": self._emit(request, rid, "supervised_handoff_verification_blocked", vid, side)
        elif status == "failed_internal": self._emit(request, rid, "supervised_handoff_verification_failed_internal", vid, side)
        return self._finish(request, vid, rid, policy.policy_id, status, vrd, safe, before, {"safe_apply_executed": True, "verification_executed": verification_executed}, ctx, eval_result_id, dec, fs, changed, snap, warnings, errs, {"side_effects": side, "validation_errors": val_errors, "context_refresh_status": ctx_status, "verification_attempted": verification_attempted, "evaluator_attempted": evaluator_attempted, "metadata_updated": True}, handoff)

    def _load_safe_apply(self,pool_id,eid):
        p=Path(self.storage.root_dir)/"atlas"/"supervised_handoff_safe_apply"/validate_relative_path(pool_id)/f"{validate_relative_path(eid)}.json"
        return json.loads(p.read_text(encoding="utf-8"))
    def _load_handoff(self,pool_id,hid):
        if not hid: return None,"handoff_missing"
        p=Path(self.storage.root_dir)/"atlas"/"safe_apply_handoffs"/validate_relative_path(pool_id)/f"{validate_relative_path(hid)}.json"
        if not p.exists(): return None,"handoff_missing"
        return json.loads(p.read_text(encoding="utf-8")),""

    def _finish(self, req, vid, rid, policy_id, status, vr, safe, before, after, ctx, eid, dec, fs, changed, snap, warns, errs, meta, handoff=None):
        now=datetime.now(timezone.utc).isoformat(); result_path=f"ca_data/atlas/supervised_handoff_verification/{req.pool_id}/{vid}.json"
        res=AtlasSupervisedHandoffVerificationResult(pool_id=req.pool_id,item_id=req.item_id,run_id=req.run_id,handoff_id=req.handoff_id or str((safe or {}).get("handoff_id") or ""),safe_apply_execution_id=req.safe_apply_execution_id,verification_run_id=vid,policy_id=policy_id,status=status,verification_result=vr,safe_apply_execution_result=safe,handoff_status_before=before,handoff_status_after=after,context_bundle_id=ctx,evaluator_result_id=eid,evaluator_decision=dec,failure_stop_suggestion=fs,changed_files=changed,snapshot_id=snap,warnings=warns,errors=errs,metadata=meta,created_at=now)
        d=Path(self.storage.root_dir)/"atlas"/"supervised_handoff_verification"/req.pool_id; d.mkdir(parents=True,exist_ok=True)
        (d/f"{vid}.json").write_text(json.dumps(res.model_dump(),ensure_ascii=False,indent=2),encoding="utf-8")

        if handoff is not None:
            handoff.update({"verification_executed": bool(after.get("verification_executed")), "verification_run_id": vid, "verification_result_path": result_path, "verification_executed_at": now, "verification_status": status, "evaluator_result_id": eid, "evaluator_decision": dec, "context_bundle_id": ctx})
            if status == "failed" and fs: handoff["failure_stop_suggestion"] = fs
            md = handoff.setdefault("metadata", {})
            md["last_verification_status"] = status; md["last_verification_run_id"] = vid; md["last_evaluator_decision"] = dec
            md["side_effects"] = self._side_effects(bool(after.get("verification_executed")))
            hp=Path(self.storage.root_dir)/"atlas"/"safe_apply_handoffs"/req.pool_id/f"{res.handoff_id}.json"; hp.write_text(json.dumps(handoff,ensure_ascii=False,indent=2),encoding="utf-8")

        pool=self.storage.load_pool(req.pool_id); item=pool.get_item(req.item_id)
        if item:
            item.metadata=dict(item.metadata or {})
            rows=list(item.metadata.get("supervised_handoff_verification_results") or [])
            rows.append({"verification_run_id":vid,"handoff_id":res.handoff_id,"safe_apply_execution_id":req.safe_apply_execution_id,"status":status,"verification_status":(vr or {}).get("status",status),"evaluator_result_id":eid,"evaluator_decision":dec,"context_bundle_id":ctx,"changed_files":changed,"snapshot_id":snap,"created_at":now,"result_path":result_path,"failure_stop_suggestion":fs if status=="failed" else {}})
            item.metadata["supervised_handoff_verification_results"]=rows
            item.metadata["latest_supervised_handoff_verification_result_id"]=vid
            hs=list(item.metadata.get("safe_apply_handoffs") or [])
            for h in hs:
                if h.get("handoff_id")==res.handoff_id:
                    h.update({"verification_executed":bool(after.get("verification_executed")),"verification_run_id":vid,"verification_status":status,"evaluator_result_id":eid,"evaluator_decision":dec})
            item.metadata["safe_apply_handoffs"]=hs
            self.storage.save_pool(pool)

        self._emit(req, rid, "supervised_handoff_verification_result_saved", vid, self._side_effects(bool(after.get("verification_executed"))))
        return res

    def _side_effects(self, verification_executed: bool):
        return {"safe_apply_executed":True,"verification_executed":verification_executed,"bounded_retry_executed":False,"rollback_executed":False,"restore_executed":False,"debug_review_executed":False,"patch_regeneration_executed":False,"safe_apply_rerun_executed":False}

    def _emit(self, req, rid, event_type, vid, side_effects, extra=None):
        payload={"event_type":event_type,"verification_run_id":vid,"pool_id":req.pool_id,"item_id":req.item_id,"run_id":rid,"handoff_id":req.handoff_id,"safe_apply_execution_id":req.safe_apply_execution_id,**side_effects,"created_at":datetime.now(timezone.utc).isoformat()}
        if extra: payload.update(extra)
        self.journal.append_event(req.pool_id, rid, payload)
