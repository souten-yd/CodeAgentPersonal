from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agent.atlas_auto_safe_apply_schema import AtlasAutoSafeApplyRequest
from agent.atlas_auto_verification_schema import AtlasAutoVerificationRequest
from agent.atlas_context_refresh_schema import AtlasContextRefreshRequest
from agent.atlas_dev_tool_path import validate_relative_path
from agent.atlas_failure_stop_service import AtlasFailureStopService
from agent.atlas_llm_evaluator_schema import AtlasEvaluatorRequest
from agent.atlas_multi_item_autopilot_policies import get_multi_item_policy
from agent.atlas_multi_item_autopilot_schema import (
    AtlasAutopilotItemResult,
    AtlasMultiItemAutopilotRequest,
    AtlasMultiItemAutopilotResult,
)


class AtlasMultiItemAutopilotService:
    def __init__(self, *, storage, journal, automation_gate, auto_safe_apply_service, auto_verification_service, context_refresh_service, evaluator_service):
        self.storage = storage
        self.journal = journal
        self.automation_gate = automation_gate
        self.auto_safe_apply_service = auto_safe_apply_service
        self.auto_verification_service = auto_verification_service
        self.context_refresh_service = context_refresh_service
        self.evaluator_service = evaluator_service
        self.failure_stop_service = AtlasFailureStopService(journal=journal)

    def run(self, request: AtlasMultiItemAutopilotRequest) -> AtlasMultiItemAutopilotResult:
        pool = self.storage.load_pool(request.pool_id)
        policy = get_multi_item_policy(request.policy_id)
        run_id = request.run_id
        autopilot_run_id = f"auto_{uuid4().hex[:10]}"
        started = datetime.now(timezone.utc)
        out = AtlasMultiItemAutopilotResult(pool_id=pool.pool_id, run_id=run_id, autopilot_run_id=autopilot_run_id, policy_id=policy.policy_id, status="dry_run" if request.dry_run else "completed", created_at=started.isoformat())
        self.emit("multi_item_autopilot_started", request, autopilot_run_id, status="started")
        ids = request.item_ids or [i.item_id for i in pool.items]
        changed_total = 0
        for idx, item_id in enumerate(ids):
            if out.processed_count >= min(request.max_items, policy.max_items):
                out.status, out.stop_reason = "stopped", "max_items_reached"; break
            if (datetime.now(timezone.utc) - started).total_seconds() > min(request.max_runtime_seconds, policy.max_runtime_seconds):
                out.status, out.stop_reason = "stopped", "max_runtime_seconds_exceeded"; break
            item = pool.get_item(item_id)
            if item is None:
                out.item_results.append(AtlasAutopilotItemResult(item_id=item_id, status="skipped", reason="item_not_found")); out.skipped_count += 1; continue
            self.emit("multi_item_autopilot_item_started", request, autopilot_run_id, item_id=item_id, item_index=idx, status="started")
            risk = str(getattr(item, "risk_level", "")).lower()
            approval = str(((item.metadata or {}).get("approval") or {}).get("decision") or "").lower()
            if request.require_approval and approval != "approved":
                out.item_results.append(AtlasAutopilotItemResult(item_id=item_id, status="skipped", reason="approval_required")); out.skipped_count += 1; continue
            if risk not in set(policy.allowed_risk_levels):
                out.item_results.append(AtlasAutopilotItemResult(item_id=item_id, status="skipped", reason="risk_not_allowed")); out.skipped_count += 1; continue
            if request.dry_run or policy.policy_id == "dry_run_multi_item_v1":
                out.item_results.append(AtlasAutopilotItemResult(item_id=item_id, status="dry_run", reason="eligible")); out.processed_count += 1; continue
            result = AtlasAutopilotItemResult(item_id=item_id, status="failed")
            if request.include_context_refresh:
                ctx = self.context_refresh_service.refresh(AtlasContextRefreshRequest(pool_id=pool.pool_id, item_id=item_id, run_id=run_id, trigger="pre_safe_apply", workspace_id=request.workspace_id, project_path=request.project_path or pool.project_path, changed_files=list(getattr(item, "target_files", []) or []), policy_id=request.context_policy_id, include_local_tools=True, include_nexus_search=False, include_deep_research=False))
                result.context_bundle_id = ctx.bundle_id
                self.emit("multi_item_autopilot_context_refresh_completed", request, autopilot_run_id, item_id=item_id, item_index=idx, status=ctx.status, context_bundle_id=ctx.bundle_id)
                if ctx.status in {"blocked", "failed"} and policy.require_context_refresh:
                    result.status, result.reason = "blocked", "context_refresh_failed"
                    out.item_results.append(result); out.blocked_count += 1; out.processed_count += 1; out.status = "stopped"; out.stop_reason = result.reason; break
            safe = self.auto_safe_apply_service.execute_one(AtlasAutoSafeApplyRequest(pool_id=pool.pool_id, item_id=item_id, run_id=run_id, workspace_id=request.workspace_id))
            result.safe_apply_result = safe.model_dump()
            self.emit("multi_item_autopilot_safe_apply_completed", request, autopilot_run_id, item_id=item_id, item_index=idx, status=safe.status)
            if safe.status != "applied":
                result.status, result.reason = "failed", "safe_apply_not_applied"
                out.item_results.append(result); out.failed_count += 1; out.processed_count += 1; out.status = "stopped"; out.stop_reason = result.reason; break
            vr = self.auto_verification_service.run_after_auto_safe_apply(AtlasAutoVerificationRequest(pool_id=pool.pool_id, item_id=item_id, run_id=run_id))
            result.verification_result = vr.model_dump()
            self.emit("multi_item_autopilot_verification_completed", request, autopilot_run_id, item_id=item_id, item_index=idx, status=vr.status)
            if vr.status != "passed":
                result.failure_stop_suggestion = self.failure_stop_service.build_for_verification_failure(pool, item, run_id, vr.model_dump()).model_dump()
            ev = None
            if request.include_evaluator:
                ev = self.evaluator_service.evaluate(AtlasEvaluatorRequest(pool_id=pool.pool_id, item_id=item_id, run_id=run_id, trigger="verification_failure" if vr.status == "failed" else "post_verification", context_bundle_id=result.context_bundle_id, use_latest_context_bundle=False, project_path=request.project_path or pool.project_path, changed_files=list(getattr(item, "target_files", []) or []), verification_result=vr.model_dump(), safe_apply_result=safe.model_dump(), failure_stop_suggestion=result.failure_stop_suggestion, policy_id=request.evaluator_policy_id, metadata={"autopilot_run_id": autopilot_run_id, "item_index": idx}))
                result.evaluator_result_id = str((ev.metadata or {}).get("eval_id") or "")
                result.evaluator_decision = ev.decision.model_dump()
                self.emit("multi_item_autopilot_evaluator_completed", request, autopilot_run_id, item_id=item_id, item_index=idx, status=ev.status, evaluator_result_id=result.evaluator_result_id, evaluator_decision=result.evaluator_decision)
            decision = str((result.evaluator_decision or {}).get("decision") or "")
            result.changed_files = list((safe.changed_files if hasattr(safe, 'changed_files') else []) or [])
            changed_total += len(result.changed_files)
            if changed_total > min(request.max_changed_files_total, policy.max_changed_files_total):
                result.status, result.reason = "stopped", "max_changed_files_total_exceeded"; out.status = "stopped"; out.stop_reason = result.reason
            elif vr.status == "failed":
                result.status, result.reason = "failed", "verification_failed"; out.status = "stopped"; out.stop_reason = result.reason
            elif decision in set(policy.stop_decisions) and (decision != "manual_required" or request.stop_on_manual_required) and (decision != "revise" or request.stop_on_revise):
                result.status, result.reason = "stopped", f"evaluator_{decision}"; out.status = "stopped"; out.stop_reason = result.reason
            else:
                result.status = "completed"
            out.item_results.append(result); out.processed_count += 1
            out.completed_count += 1 if result.status == "completed" else 0
            out.failed_count += 1 if result.status == "failed" else 0
            out.blocked_count += 1 if result.status == "blocked" else 0
            if out.failed_count >= min(request.max_failures, policy.max_failures):
                out.status, out.stop_reason = "stopped", "max_failures_reached"
            if out.status in {"stopped", "failed"}:
                break
        if out.status == "completed" and out.completed_count == 0 and out.blocked_count > 0:
            out.status = "blocked"
        if out.status == "stopped" and out.completed_count > 0:
            out.status = "partial"
        self.save_result(out)
        self.emit("multi_item_autopilot_completed", request, autopilot_run_id, status=out.status)
        return out

    def save_result(self, result: AtlasMultiItemAutopilotResult):
        validate_relative_path(result.pool_id)
        root = Path("ca_data") / "atlas" / "multi_item_autopilot" / result.pool_id
        root.mkdir(parents=True, exist_ok=True)
        (root / f"{result.autopilot_run_id}.json").write_text(json.dumps(result.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        lines = ["# Multi-item Autopilot Run", "", "## Summary"]
        for k in ["autopilot_run_id", "pool_id", "run_id", "policy_id", "status", "processed_count", "completed_count", "failed_count", "stop_reason"]:
            lines.append(f"- {k}: {getattr(result, k)}")
        lines += ["", "## Item Results"]
        for r in result.item_results:
            lines += [f"- item_id: {r.item_id}", f"  - status: {r.status}", f"  - reason: {r.reason}", f"  - context_bundle_id: {r.context_bundle_id}", f"  - evaluator_result_id: {r.evaluator_result_id}", f"  - evaluator_decision.decision: {(r.evaluator_decision or {}).get('decision','')}", f"  - verification_result.status: {(r.verification_result or {}).get('status','')}", f"  - safe_apply_result.status: {(r.safe_apply_result or {}).get('status','')}"]
        lines += ["", "## Warnings"] + ([f"- {w}" for w in result.warnings] or ["- (none)"]) + ["", "## Errors"] + ([f"- {e}" for e in result.errors] or ["- (none)"])
        (root / f"{result.autopilot_run_id}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def emit(self, event_type, request, autopilot_run_id, **kw):
        if not request.run_id:
            return
        self.journal.append_event(request.pool_id, request.run_id, {"event_type": event_type, "pool_id": request.pool_id, "run_id": request.run_id, "autopilot_run_id": autopilot_run_id, "created_at": datetime.now(timezone.utc).isoformat(), **kw})
