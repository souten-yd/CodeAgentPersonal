from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agent.atlas_auto_verification_schema import AtlasAutoVerificationRequest
from agent.atlas_bounded_retry_policies import get_bounded_retry_policy
from agent.atlas_bounded_retry_schema import AtlasBoundedRetryRequest, AtlasBoundedRetryResult, AtlasRetryAttemptResult
from agent.atlas_context_refresh_schema import AtlasContextRefreshRequest
from agent.atlas_dev_tool_path import validate_relative_path
from agent.atlas_llm_evaluator_schema import AtlasEvaluatorRequest


class AtlasBoundedRetryService:
    def __init__(self, *, storage, journal, auto_verification_service, context_refresh_service, evaluator_service):
        self.storage = storage
        self.journal = journal
        self.auto_verification_service = auto_verification_service
        self.context_refresh_service = context_refresh_service
        self.evaluator_service = evaluator_service

    def resolve_project_path(self, request, pool, item) -> str:
        return str(request.project_path or getattr(pool, "project_path", "") or getattr(item, "project_path", "") or "")

    def classify_retryability(self, verification_result: dict, failure_stop_suggestion: dict, policy) -> dict:
        status = str((verification_result or {}).get("status") or "")
        if status not in set(policy.retry_on_statuses):
            return {"retry_allowed": False, "reason": "status_not_retryable"}
        body = "\n".join(str(x) for x in [verification_result.get("stdout_tail",""), verification_result.get("stderr_tail",""), " ".join(verification_result.get("errors",[]) or []), " ".join(verification_result.get("warnings",[]) or []), failure_stop_suggestion.get("reason",""), str((failure_stop_suggestion.get("verification_result") or {}))]).lower()
        if any(p.lower() in body for p in policy.non_retryable_error_patterns):
            return {"retry_allowed": False, "reason": "deterministic_test_failure_or_code_error"}
        if any(p.lower() in body for p in policy.retryable_error_patterns):
            return {"retry_allowed": True, "reason": "transient_or_environment_suspected"}
        if status in {"blocked", "skipped"}:
            return {"retry_allowed": True, "reason": "verification_not_executed_or_blocked"}
        if status == "failed":
            return {"retry_allowed": False, "reason": "failed_but_not_classified_retryable"}
        return {"retry_allowed": False, "reason": "status_not_retryable"}

    def run(self, request: AtlasBoundedRetryRequest) -> AtlasBoundedRetryResult:
        pool = self.storage.load_pool(request.pool_id)
        item = pool.get_item(request.item_id)
        policy = get_bounded_retry_policy(request.policy_id)
        retry_run_id = f"retry_{uuid4().hex[:10]}"
        result = AtlasBoundedRetryResult(pool_id=request.pool_id, item_id=request.item_id, run_id=request.run_id, retry_run_id=retry_run_id, policy_id=policy.policy_id, status="failed")
        self.emit("bounded_retry_started", request, retry_run_id, attempt_index=0)
        cl = self.classify_retryability(request.verification_result, request.failure_stop_suggestion, policy)
        self.emit("bounded_retry_classified", request, retry_run_id, retry_allowed=cl["retry_allowed"], retry_reason=cl["reason"], verification_status=(request.verification_result or {}).get("status", ""))
        if not cl["retry_allowed"]:
            result.status, result.stop_reason = "not_retryable", cl["reason"]
            result.attempts.append(AtlasRetryAttemptResult(attempt_index=1, status="retry_skipped", retry_allowed=False, retry_reason=cl["reason"], verification_result=request.verification_result))
            result.attempt_count = 1
            self.save_result(result)
            self.emit("bounded_retry_not_retryable", request, retry_run_id, attempt_index=1, retry_allowed=False, retry_reason=cl["reason"])
            return result
        if request.dry_run or policy.policy_id == "verification_retry_dry_run_v1":
            result.status, result.stop_reason = "dry_run", "dry_run_only"
            result.attempts.append(AtlasRetryAttemptResult(attempt_index=1, status="retry_skipped", retry_allowed=True, retry_reason=cl["reason"], verification_result=request.verification_result))
            result.attempt_count = 1
            self.save_result(result)
            return result
        max_attempts = min(request.max_attempts, policy.max_attempts)
        changed_files = list(request.changed_files or [])
        for i in range(1, max_attempts + 1):
            ctx_id = ""
            project_path = self.resolve_project_path(request, pool, item)
            if policy.allow_context_refresh:
                ctx = self.context_refresh_service.refresh(AtlasContextRefreshRequest(pool_id=request.pool_id, item_id=request.item_id, run_id=request.run_id, trigger="verification_failure", workspace_id=request.workspace_id, project_path=project_path, changed_files=changed_files, policy_id=request.context_policy_id, include_local_tools=True, include_nexus_search=False, include_deep_research=False))
                ctx_id = ctx.bundle_id
                self.emit("bounded_retry_context_refresh_completed", request, retry_run_id, attempt_index=i, context_bundle_id=ctx_id)
            self.emit("bounded_retry_verification_started", request, retry_run_id, attempt_index=i)
            vr = self.auto_verification_service.run_after_auto_safe_apply(AtlasAutoVerificationRequest(pool_id=request.pool_id, item_id=request.item_id, run_id=request.run_id))
            self.emit("bounded_retry_verification_completed", request, retry_run_id, attempt_index=i, verification_status=vr.status)
            ev = self.evaluator_service.evaluate(AtlasEvaluatorRequest(pool_id=request.pool_id, item_id=request.item_id, run_id=request.run_id, trigger="post_verification" if vr.status == "passed" else "verification_failure", context_bundle_id=ctx_id, use_latest_context_bundle=False, project_path=project_path, changed_files=changed_files, verification_result=vr.model_dump(), safe_apply_result=request.safe_apply_result, failure_stop_suggestion=request.failure_stop_suggestion, policy_id=request.evaluator_policy_id, metadata={"retry_run_id": retry_run_id, "attempt_index": i, "bounded_retry": True})) if policy.allow_evaluator else None
            decision = (ev.decision.model_dump() if ev else {})
            attempt_status = "verification_passed" if vr.status == "passed" else f"verification_{vr.status}" if vr.status in {"failed", "blocked", "skipped"} else "failed"
            ar = AtlasRetryAttemptResult(attempt_index=i, status=attempt_status, retry_allowed=True, retry_reason=cl["reason"], verification_result=vr.model_dump(), context_bundle_id=ctx_id, evaluator_result_id=str((ev.metadata or {}).get("eval_id") or "") if ev else "", evaluator_decision=decision)
            result.attempts.append(ar)
            result.attempt_count = len(result.attempts)
            result.final_verification_status = vr.status
            if decision.get("decision") in {"stop", "manual_required", "revise"}:
                result.status, result.stop_reason = "stopped", f"evaluator_{decision.get('decision')}"
                self.emit("bounded_retry_stopped", request, retry_run_id, attempt_index=i, evaluator_decision=decision.get("decision"))
                break
            if vr.status == "passed":
                result.status = "recovered"
                self.emit("bounded_retry_recovered", request, retry_run_id, attempt_index=i)
                break
            if i == max_attempts:
                result.status, result.stop_reason = "exhausted", "max_attempts_exhausted"
                self.emit("bounded_retry_exhausted", request, retry_run_id, attempt_index=i)
        self.save_result(result)
        return result

    def save_result(self, result: AtlasBoundedRetryResult):
        validate_relative_path(result.pool_id)
        root = Path("ca_data") / "atlas" / "bounded_retry" / result.pool_id
        root.mkdir(parents=True, exist_ok=True)
        (root / f"{result.retry_run_id}.json").write_text(json.dumps(result.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        lines = ["# Bounded Retry Run", "", "## Summary"]
        for k in ["retry_run_id", "pool_id", "item_id", "run_id", "policy_id", "status", "attempt_count", "final_verification_status", "stop_reason"]:
            lines.append(f"- {k}: {getattr(result, k)}")
        lines += ["", "## Attempts"]
        for a in result.attempts:
            lines += [f"- attempt_index: {a.attempt_index}", f"  - status: {a.status}", f"  - retry_allowed: {a.retry_allowed}", f"  - retry_reason: {a.retry_reason}", f"  - verification_result.status: {(a.verification_result or {}).get('status','')}", f"  - evaluator_result_id: {a.evaluator_result_id}", f"  - evaluator_decision.decision: {(a.evaluator_decision or {}).get('decision','')}"]
        lines += ["", "## Safety", "- safe_apply_rerun: false", "- auto_restore: false", "- auto_rollback: false", "- auto_debug_review: false", "- auto_patch_regeneration: false", "", "## Warnings"]
        lines += ([f"- {w}" for w in result.warnings] or ["- (none)"])
        lines += ["", "## Errors"] + ([f"- {e}" for e in result.errors] or ["- (none)"])
        (root / f"{result.retry_run_id}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def emit(self, event_type, request, retry_run_id, **kw):
        if request.run_id:
            self.journal.append_event(request.pool_id, request.run_id, {"event_type": event_type, "pool_id": request.pool_id, "item_id": request.item_id, "run_id": request.run_id, "retry_run_id": retry_run_id, "created_at": datetime.now(timezone.utc).isoformat(), **kw})
