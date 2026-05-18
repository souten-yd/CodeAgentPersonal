from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agent.atlas_auto_verification_service import AtlasAutoVerificationService
from agent.atlas_bounded_retry_schema import AtlasBoundedRetryRequest
from agent.atlas_bounded_retry_service import AtlasBoundedRetryService
from agent.atlas_context_refresh_service import AtlasContextRefreshService
from agent.atlas_dev_tool_path import validate_relative_path
from agent.atlas_journal import AtlasJournal
from agent.atlas_llm_evaluator_service import AtlasLLMEvaluatorService
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_supervised_handoff_retry_policies import get_supervised_handoff_retry_policy
from agent.atlas_supervised_handoff_retry_schema import AtlasSupervisedHandoffRetryRequest, AtlasSupervisedHandoffRetryResult
from agent.test_command_runner import TestCommandRunner


class AtlasSupervisedHandoffRetryService:
    def __init__(self, *, storage=None, journal=None, bounded_retry_service=None):
        self.storage = storage or AtlasPlanPoolStorage(Path("ca_data"))
        self.journal = journal or AtlasJournal(Path("ca_data"))
        self.bounded_retry_service = bounded_retry_service or AtlasBoundedRetryService(
            storage=self.storage,
            journal=self.journal,
            auto_verification_service=AtlasAutoVerificationService(journal=self.journal, storage=self.storage, command_runner=TestCommandRunner()),
            context_refresh_service=AtlasContextRefreshService(journal=self.journal),
            evaluator_service=AtlasLLMEvaluatorService(journal=self.journal),
        )

    def run(self, request: AtlasSupervisedHandoffRetryRequest) -> AtlasSupervisedHandoffRetryResult:
        retry_id = f"retryhandoff_{uuid4().hex[:12]}"; rid = request.run_id or retry_id
        res = None
        try:
            policy = get_supervised_handoff_retry_policy(request.policy_id)
            self._emit(request, rid, "supervised_handoff_retry_started", retry_id)
            ver = self._load_json("supervised_handoff_verification", request.pool_id, request.verification_run_id, "verifyhandoff_")
            safe = self._load_json("supervised_handoff_safe_apply", request.pool_id, request.safe_apply_execution_id, "safehandoff_")
            handoff_id = request.handoff_id or str(ver.get("handoff_id") or safe.get("handoff_id") or "")
            handoff = self._load_json("safe_apply_handoffs", request.pool_id, handoff_id, "handoff_")
            self._emit(request, rid, "supervised_handoff_retry_input_loaded", retry_id, handoff_id=handoff_id)
            validation_errors = self.validate_retry_eligibility(request, policy, ver, safe, handoff)
            cl = self._classify(ver)
            self._emit(request, rid, "supervised_handoff_retry_validation_completed", retry_id, validation_errors=validation_errors)
            self._emit(request, rid, "supervised_handoff_retry_classified", retry_id, retry_allowed=cl.get("retry_allowed"), retry_reason=cl.get("reason"), original_verification_status=cl.get("original_status"))
            orig_status = cl.get("original_status", "")
            status = "dry_run" if request.dry_run else "not_retryable"
            br = {}
            bounded_retry_run_id = ""
            final_verification_status = orig_status
            if validation_errors:
                status = "blocked"
            elif cl.get("retry_allowed") and not request.dry_run and policy.allow_bounded_retry:
                self._emit(request, rid, "supervised_handoff_bounded_retry_started", retry_id)
                b = self.bounded_retry_service.run(AtlasBoundedRetryRequest(pool_id=request.pool_id, item_id=request.item_id, run_id=rid, workspace_id=request.workspace_id, project_path=request.project_path, policy_id=request.bounded_retry_policy_id, context_policy_id=request.context_policy_id, evaluator_policy_id=request.evaluator_policy_id, verification_result=ver.get("verification_result") or {}, safe_apply_result=safe.get("safe_apply_result") or {}, failure_stop_suggestion=ver.get("failure_stop_suggestion") or {}, context_bundle_id=str(ver.get("context_bundle_id") or ""), changed_files=list(ver.get("changed_files") or []), max_attempts=request.max_attempts, dry_run=False, metadata={"source": "supervised_handoff_retry"}))
                br = b.model_dump(); bounded_retry_run_id = b.retry_run_id; final_verification_status = b.final_verification_status or orig_status
                status = "failed_internal" if b.status == "failed" else b.status
                self._emit(request, rid, "supervised_handoff_bounded_retry_completed", retry_id, bounded_retry_run_id=bounded_retry_run_id)
            elif not request.dry_run:
                status = "not_retryable"

            patch_regen = status in {"not_retryable", "exhausted", "stopped"}
            res = AtlasSupervisedHandoffRetryResult(pool_id=request.pool_id, item_id=request.item_id, run_id=rid, handoff_id=handoff_id, safe_apply_execution_id=request.safe_apply_execution_id, verification_run_id=request.verification_run_id, supervised_retry_run_id=retry_id, bounded_retry_run_id=bounded_retry_run_id, policy_id=policy.policy_id, bounded_retry_policy_id=request.bounded_retry_policy_id, status=status, original_verification_status=orig_status, final_verification_status=final_verification_status, bounded_retry_result=br, retryability=cl, failure_stop_suggestion=ver.get("failure_stop_suggestion") or {}, changed_files=list(ver.get("changed_files") or []), snapshot_id=str(safe.get("snapshot_id") or ""), errors=[f"validation_errors:{','.join(validation_errors)}"] if validation_errors else [], metadata={"validation_errors": validation_errors, "retryability": cl, "would_retry": bool(cl.get("retry_allowed")), "bounded_retry_called": bool(bounded_retry_run_id), "duplicate_retry_detected": any("duplicate_retry" in e for e in validation_errors), "patch_regen_recommended": patch_regen, "patch_regen_reason": cl.get("reason") if patch_regen else "", "metadata_updated": False, "side_effects": {"safe_apply_rerun_executed": False, "bounded_retry_executed": bool(bounded_retry_run_id), "rollback_executed": False, "restore_executed": False, "debug_review_executed": False, "patch_regeneration_executed": False}})
            self._update_metadata(request, res, handoff)
            res.metadata["metadata_updated"] = True
            self._save(res)
            self._emit(request, rid, f"supervised_handoff_retry_{res.status}", retry_id, retry_allowed=cl.get("retry_allowed"), retry_reason=cl.get("reason"), original_verification_status=orig_status, final_verification_status=final_verification_status)
            self._emit(request, rid, "supervised_handoff_retry_result_saved", retry_id)
            return res
        except Exception as exc:
            if res is None:
                res = AtlasSupervisedHandoffRetryResult(pool_id=request.pool_id, item_id=request.item_id, run_id=rid, handoff_id=request.handoff_id or "", safe_apply_execution_id=request.safe_apply_execution_id, verification_run_id=request.verification_run_id, supervised_retry_run_id=retry_id, policy_id=request.policy_id, bounded_retry_policy_id=request.bounded_retry_policy_id, status="failed_internal", errors=[f"bounded_retry_exception:{type(exc).__name__}"], metadata={"metadata_updated": False, "side_effects": {"safe_apply_rerun_executed": False, "bounded_retry_executed": False, "rollback_executed": False, "restore_executed": False, "debug_review_executed": False, "patch_regeneration_executed": False}})
            else:
                res.status = "failed_internal"; res.errors.append(f"bounded_retry_exception:{type(exc).__name__}")
            self._save(res)
            self._emit(request, rid, "supervised_handoff_retry_failed_internal", retry_id)
            self._emit(request, rid, "supervised_handoff_retry_result_saved", retry_id)
            return res

    def validate_retry_eligibility(self, request, policy, ver, safe, handoff) -> list[str]:
        errs = []
        vstatus = str((ver.get("verification_result") or {}).get("status") or ver.get("status") or "")
        if ver.get("pool_id") and ver.get("pool_id") != request.pool_id: errs.append("verification_pool_mismatch")
        if ver.get("item_id") and ver.get("item_id") != request.item_id: errs.append("verification_item_mismatch")
        if ver.get("safe_apply_execution_id") and ver.get("safe_apply_execution_id") != request.safe_apply_execution_id: errs.append("verification_safe_apply_execution_id_mismatch")
        if request.handoff_id and str(ver.get("handoff_id") or "") != request.handoff_id: errs.append("verification_handoff_mismatch")
        if vstatus in {"passed", "evaluator_manual_required", "evaluator_stop"} or vstatus not in set(policy.allow_retry_on_statuses): errs.append("verification_status_not_retryable")
        vse = ((ver.get("metadata") or {}).get("side_effects") or {})
        for k in ["safe_apply_rerun_executed", "bounded_retry_executed", "rollback_executed", "restore_executed", "patch_regeneration_executed"]:
            if bool(vse.get(k)): errs.append(f"verification_side_effect_{k}")
        if safe.get("pool_id") and safe.get("pool_id") != request.pool_id: errs.append("safe_apply_pool_mismatch")
        if safe.get("item_id") and safe.get("item_id") != request.item_id: errs.append("safe_apply_item_mismatch")
        if safe.get("status") != "applied": errs.append("safe_apply_not_applied")
        if not safe.get("safe_apply_result"): errs.append("safe_apply_result_missing")
        if not safe.get("changed_files") and safe.get("changed_files") != []: errs.append("safe_apply_changed_files_missing")
        sse = ((safe.get("metadata") or {}).get("side_effects") or {})
        if not bool(sse.get("safe_apply_executed")): errs.append("safe_apply_side_effect_missing")
        if bool(sse.get("verification_executed")): errs.append("safe_apply_verification_already_executed")
        if handoff.get("pool_id") and handoff.get("pool_id") != request.pool_id: errs.append("handoff_pool_mismatch")
        if handoff.get("item_id") and handoff.get("item_id") != request.item_id: errs.append("handoff_item_mismatch")
        if not bool(handoff.get("safe_apply_executed")): errs.append("handoff_safe_apply_not_executed")
        if str(handoff.get("safe_apply_execution_id") or "") != request.safe_apply_execution_id: errs.append("handoff_safe_apply_execution_id_mismatch")
        hv = str(handoff.get("verification_run_id") or (handoff.get("metadata") or {}).get("last_verification_run_id") or "")
        if hv and hv != request.verification_run_id: errs.append("handoff_verification_run_mismatch")
        if str(handoff.get("verification_status") or "") not in {"failed", "blocked", "skipped"}: errs.append("handoff_verification_status_not_retryable")
        for row in (handoff.get("metadata") or {}).get("supervised_handoff_retry_results") or []:
            if str(row.get("original_verification_run_id") or "") == request.verification_run_id and str(row.get("status") or "") in {"recovered", "exhausted", "stopped"}:
                errs.append("duplicate_retry_for_verification"); break
        return errs

    def _load_json(self, kind, pool_id, run_id, prefix):
        if prefix and not str(run_id).startswith(prefix):
            raise ValueError(f"invalid_id:{kind}")
        p = Path(self.storage.root_dir) / "atlas" / kind / validate_relative_path(pool_id) / f"{validate_relative_path(run_id)}.json"
        return json.loads(p.read_text(encoding="utf-8"))

    def _classify(self, ver):
        st = str((ver.get("verification_result") or {}).get("status") or ver.get("status") or "")
        body = json.dumps(ver, ensure_ascii=False).lower()
        det = any(x in body for x in ["assertionerror", "syntaxerror", "typeerror", "nameerror", "failed test", "expected", "actual"])
        tr = any(x in body for x in ["timeout", "runner unavailable", "environment", "transient"])
        if st == "passed": reason, allowed = "status_not_retryable", False
        elif det: reason, allowed = "deterministic_test_failure_or_code_error", False
        elif tr: reason, allowed = "transient_or_environment_suspected", True
        elif st in {"blocked", "skipped"}: reason, allowed = "verification_not_executed_or_blocked", True
        elif st == "failed": reason, allowed = "failed_but_not_classified_retryable", False
        else: reason, allowed = "status_not_retryable", False
        return {"retry_allowed": allowed, "reason": reason, "classification_source": "AtlasBoundedRetryService.classify_retryability_compatible", "deterministic_failure_detected": det, "transient_failure_detected": tr, "original_status": st}

    def _update_metadata(self, req, res, handoff):
        pool = self.storage.load_pool(req.pool_id); item = pool.get_item(req.item_id)
        item.metadata = dict(item.metadata or {})
        rows = list(item.metadata.get("supervised_handoff_retry_results") or [])
        rows.append({"supervised_retry_run_id": res.supervised_retry_run_id, "status": res.status, "original_verification_run_id": res.verification_run_id})
        item.metadata["supervised_handoff_retry_results"] = rows; item.metadata["latest_supervised_handoff_retry_result_id"] = res.supervised_retry_run_id
        for h in (item.metadata.get("safe_apply_handoffs") or []):
            if h.get("safe_apply_execution_id") == res.safe_apply_execution_id:
                h.update({"last_supervised_handoff_retry_status": res.status, "last_supervised_handoff_retry_run_id": res.supervised_retry_run_id, "last_bounded_retry_run_id": res.bounded_retry_run_id, "recovered_by_bounded_retry": res.status == "recovered", "patch_regen_recommended": bool(res.metadata.get("patch_regen_recommended")), "patch_regen_reason": res.metadata.get("patch_regen_reason", "")})
        self.storage.save_pool(pool)
        handoff.setdefault("metadata", {})
        handoff["metadata"].setdefault("supervised_handoff_retry_results", []).append({"supervised_retry_run_id": res.supervised_retry_run_id, "bounded_retry_run_id": res.bounded_retry_run_id, "original_verification_run_id": res.verification_run_id, "status": res.status})
        handoff["metadata"].update({"last_supervised_handoff_retry_status": res.status, "last_supervised_handoff_retry_run_id": res.supervised_retry_run_id, "last_bounded_retry_run_id": res.bounded_retry_run_id, "last_retryability": res.retryability, "last_retry_reason": res.retryability.get("reason", "")})
        if res.status == "recovered":
            handoff["verification_status"] = "passed"; handoff["metadata"].update({"recovered_by_bounded_retry": True, "recovered_retry_run_id": res.supervised_retry_run_id, "last_verification_status": "passed"})
        if res.status in {"not_retryable", "exhausted", "stopped"}:
            handoff["metadata"].update({"patch_regen_recommended": True, "patch_regen_reason": res.metadata.get("patch_regen_reason") or res.status, "recommended_regen_source": "supervised_handoff_retry"})
        hp = Path(self.storage.root_dir) / "atlas" / "safe_apply_handoffs" / req.pool_id / f"{res.handoff_id}.json"
        hp.write_text(json.dumps(handoff, ensure_ascii=False, indent=2), encoding="utf-8")

    def _save(self, res):
        d = Path(self.storage.root_dir) / "atlas" / "supervised_handoff_retry" / res.pool_id; d.mkdir(parents=True, exist_ok=True)
        (d / f"{res.supervised_retry_run_id}.json").write_text(json.dumps(res.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        (d / f"{res.supervised_retry_run_id}.md").write_text(f"# Supervised Handoff Retry\n\n- status: {res.status}\n", encoding="utf-8")

    def _emit(self, req, rid, event, retry_id, **kw):
        self.journal.append_event(req.pool_id, rid, {"event_type": event, "supervised_retry_run_id": retry_id, "verification_run_id": req.verification_run_id, "pool_id": req.pool_id, "item_id": req.item_id, "run_id": rid, "handoff_id": req.handoff_id, "safe_apply_execution_id": req.safe_apply_execution_id, "retry_allowed": kw.get("retry_allowed"), "retry_reason": kw.get("retry_reason"), "original_verification_status": kw.get("original_verification_status"), "final_verification_status": kw.get("final_verification_status"), "created_at": datetime.now(timezone.utc).isoformat(), "safe_apply_rerun_executed": False, "rollback_executed": False, "restore_executed": False, "debug_review_executed": False, "patch_regeneration_executed": False, **kw})
