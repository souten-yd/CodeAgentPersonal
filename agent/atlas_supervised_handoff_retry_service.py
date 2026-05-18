from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agent.atlas_bounded_retry_schema import AtlasBoundedRetryRequest
from agent.atlas_bounded_retry_service import AtlasBoundedRetryService
from agent.atlas_dev_tool_path import validate_relative_path
from agent.atlas_journal import AtlasJournal
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_supervised_handoff_retry_policies import get_supervised_handoff_retry_policy
from agent.atlas_supervised_handoff_retry_schema import AtlasSupervisedHandoffRetryRequest, AtlasSupervisedHandoffRetryResult


class AtlasSupervisedHandoffRetryService:
    def __init__(self, *, storage=None, journal=None, bounded_retry_service=None):
        self.storage = storage or AtlasPlanPoolStorage(Path("ca_data"))
        self.journal = journal or AtlasJournal(Path("ca_data"))
        self.bounded_retry_service = bounded_retry_service

    def run(self, request: AtlasSupervisedHandoffRetryRequest) -> AtlasSupervisedHandoffRetryResult:
        policy = get_supervised_handoff_retry_policy(request.policy_id)
        retry_id = f"retryhandoff_{uuid4().hex[:12]}"; rid = request.run_id or retry_id
        ver = self._load_json("supervised_handoff_verification", request.pool_id, request.verification_run_id, "verifyhandoff_")
        safe = self._load_json("supervised_handoff_safe_apply", request.pool_id, request.safe_apply_execution_id, "")
        handoff_id = request.handoff_id or str(ver.get("handoff_id") or safe.get("handoff_id") or "")
        handoff = self._load_json("safe_apply_handoffs", request.pool_id, handoff_id, "handoff_")
        orig_status = str((ver.get("verification_result") or {}).get("status") or ver.get("status") or "")
        cl = self._classify(ver)
        status = "dry_run" if request.dry_run else "not_retryable"
        br = {}
        bounded_retry_run_id = ""
        final_verification_status = orig_status
        if cl.get("retry_allowed") and not request.dry_run and policy.allow_bounded_retry:
            self._emit(request, rid, "supervised_handoff_bounded_retry_started", retry_id)
            svc = self.bounded_retry_service
            if svc is None:
                raise RuntimeError("bounded_retry_service_required")
            b = svc.run(AtlasBoundedRetryRequest(pool_id=request.pool_id, item_id=request.item_id, run_id=rid, workspace_id=request.workspace_id, project_path=request.project_path, policy_id=request.bounded_retry_policy_id, context_policy_id=request.context_policy_id, evaluator_policy_id=request.evaluator_policy_id, verification_result=ver.get("verification_result") or {}, safe_apply_result=safe.get("safe_apply_result") or {}, failure_stop_suggestion=ver.get("failure_stop_suggestion") or {}, context_bundle_id=str(ver.get("context_bundle_id") or ""), changed_files=list(ver.get("changed_files") or []), max_attempts=request.max_attempts, dry_run=False, metadata={"source": "supervised_handoff_retry", "supervised_retry_run_id": retry_id, "original_verification_run_id": request.verification_run_id, "safe_apply_execution_id": request.safe_apply_execution_id, "handoff_id": handoff_id, "snapshot_id": str(safe.get('snapshot_id') or '')}))
            br = b.model_dump(); bounded_retry_run_id = b.retry_run_id; final_verification_status = b.final_verification_status or orig_status
            status = "failed_internal" if b.status == "failed" else b.status
            self._emit(request, rid, "supervised_handoff_bounded_retry_completed", retry_id)
        elif not request.dry_run:
            status = "not_retryable" if not cl.get("blocked") else "blocked"

        res = AtlasSupervisedHandoffRetryResult(pool_id=request.pool_id, item_id=request.item_id, run_id=rid, handoff_id=handoff_id, safe_apply_execution_id=request.safe_apply_execution_id, verification_run_id=request.verification_run_id, supervised_retry_run_id=retry_id, bounded_retry_run_id=bounded_retry_run_id, policy_id=policy.policy_id, bounded_retry_policy_id=request.bounded_retry_policy_id, status=status, original_verification_status=orig_status, final_verification_status=final_verification_status, bounded_retry_result=br, retryability=cl, failure_stop_suggestion=ver.get("failure_stop_suggestion") or {}, changed_files=list(ver.get("changed_files") or []), snapshot_id=str(safe.get("snapshot_id") or ""), metadata={"would_retry": bool(cl.get("retry_allowed")), "side_effects": {"safe_apply_rerun_executed": False, "bounded_retry_executed": bool(bounded_retry_run_id), "rollback_executed": False, "restore_executed": False, "debug_review_executed": False, "patch_regeneration_executed": False}})
        self._update_metadata(request, res, handoff)
        self._save(res)
        self._emit(request, rid, f"supervised_handoff_retry_{res.status}", retry_id)
        self._emit(request, rid, "supervised_handoff_retry_result_saved", retry_id)
        return res

    def _load_json(self, kind, pool_id, run_id, prefix):
        if prefix and not str(run_id).startswith(prefix):
            raise ValueError(f"invalid_id:{kind}")
        p = Path(self.storage.root_dir) / "atlas" / kind / validate_relative_path(pool_id) / f"{validate_relative_path(run_id)}.json"
        return json.loads(p.read_text(encoding="utf-8"))

    def _classify(self, ver):
        st = str((ver.get("verification_result") or {}).get("status") or ver.get("status") or "")
        txt = json.dumps(ver, ensure_ascii=False).lower()
        if st == "passed": return {"retry_allowed": False, "reason": "status_not_retryable", "blocked": True}
        if any(x in txt for x in ["assertionerror", "syntaxerror", "typeerror", "nameerror", "failed test"]): return {"retry_allowed": False, "reason": "deterministic_test_failure_or_code_error"}
        if any(x in txt for x in ["timeout", "runner unavailable", "environment", "transient"]): return {"retry_allowed": True, "reason": "transient_or_environment_suspected"}
        return {"retry_allowed": st in {"blocked", "skipped"}, "reason": "verification_not_executed_or_blocked" if st in {"blocked", "skipped"} else "failed_but_not_classified_retryable"}

    def _update_metadata(self, req, res, handoff):
        pool = self.storage.load_pool(req.pool_id); item = pool.get_item(req.item_id)
        item.metadata = dict(item.metadata or {})
        rows = list(item.metadata.get("supervised_handoff_retry_results") or [])
        rows.append({"supervised_retry_run_id": res.supervised_retry_run_id, "bounded_retry_run_id": res.bounded_retry_run_id, "handoff_id": res.handoff_id, "safe_apply_execution_id": res.safe_apply_execution_id, "verification_run_id": res.verification_run_id, "status": res.status, "original_verification_status": res.original_verification_status, "final_verification_status": res.final_verification_status, "created_at": res.created_at, "result_path": f"ca_data/atlas/supervised_handoff_retry/{res.pool_id}/{res.supervised_retry_run_id}.json"})
        item.metadata["supervised_handoff_retry_results"] = rows; item.metadata["latest_supervised_handoff_retry_result_id"] = res.supervised_retry_run_id
        self.storage.save_pool(pool)
        handoff.setdefault("metadata", {})
        handoff["metadata"].setdefault("supervised_handoff_retry_results", []).append({"supervised_retry_run_id": res.supervised_retry_run_id, "bounded_retry_run_id": res.bounded_retry_run_id, "original_verification_run_id": res.verification_run_id, "status": res.status, "original_verification_status": res.original_verification_status, "final_verification_status": res.final_verification_status, "created_at": res.created_at, "result_path": f"ca_data/atlas/supervised_handoff_retry/{res.pool_id}/{res.supervised_retry_run_id}.json"})
        hp = Path(self.storage.root_dir) / "atlas" / "safe_apply_handoffs" / req.pool_id / f"{res.handoff_id}.json"
        hp.write_text(json.dumps(handoff, ensure_ascii=False, indent=2), encoding="utf-8")

    def _save(self, res):
        d = Path(self.storage.root_dir) / "atlas" / "supervised_handoff_retry" / res.pool_id; d.mkdir(parents=True, exist_ok=True)
        (d / f"{res.supervised_retry_run_id}.json").write_text(json.dumps(res.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        (d / f"{res.supervised_retry_run_id}.md").write_text(f"# Supervised Handoff Retry\n\n## Summary\n- supervised_retry_run_id: {res.supervised_retry_run_id}\n- bounded_retry_run_id: {res.bounded_retry_run_id}\n- pool_id: {res.pool_id}\n- item_id: {res.item_id}\n- handoff_id: {res.handoff_id}\n- safe_apply_execution_id: {res.safe_apply_execution_id}\n- original_verification_run_id: {res.verification_run_id}\n- status: {res.status}\n- original_verification_status: {res.original_verification_status}\n- final_verification_status: {res.final_verification_status}\n", encoding="utf-8")

    def _emit(self, req, rid, event, retry_id):
        self.journal.append_event(req.pool_id, rid, {"event_type": event, "supervised_retry_run_id": retry_id, "verification_run_id": req.verification_run_id, "pool_id": req.pool_id, "item_id": req.item_id, "run_id": rid, "handoff_id": req.handoff_id, "safe_apply_execution_id": req.safe_apply_execution_id, "policy_id": req.policy_id, "bounded_retry_policy_id": req.bounded_retry_policy_id, "created_at": datetime.now(timezone.utc).isoformat(), "safe_apply_rerun_executed": False, "rollback_executed": False, "restore_executed": False, "debug_review_executed": False, "patch_regeneration_executed": False})
