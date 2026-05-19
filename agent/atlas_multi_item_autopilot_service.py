from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agent.atlas_auto_safe_apply_schema import AtlasAutoSafeApplyRequest
from agent.atlas_auto_policy_presets import atlas_auto_policy_presets
from agent.atlas_auto_verification_schema import AtlasAutoVerificationRequest
from agent.atlas_context_refresh_schema import AtlasContextRefreshRequest
from agent.atlas_bounded_retry_schema import AtlasBoundedRetryRequest
from agent.atlas_bounded_retry_service import AtlasBoundedRetryService
from agent.atlas_dev_tool_path import validate_relative_path
from agent.atlas_failure_stop_service import AtlasFailureStopService
from agent.atlas_llm_evaluator_schema import AtlasEvaluatorRequest
from agent.atlas_multi_item_autopilot_policies import get_multi_item_policy
from agent.atlas_multi_item_supervised_status_schema import AtlasMultiItemSupervisedStatusRequest
from agent.atlas_multi_item_supervised_status_service import AtlasMultiItemSupervisedStatusService
from agent.atlas_supervised_item_status_service import AtlasSupervisedItemStatusService
from agent.atlas_multi_item_autopilot_schema import (
    AtlasAutopilotItemResult,
    AtlasMultiItemAutopilotRequest,
    AtlasMultiItemAutopilotResult,
)


class AtlasMultiItemAutopilotService:
    def __init__(self, *, storage, journal, automation_gate, auto_safe_apply_service, auto_verification_service, context_refresh_service, evaluator_service, bounded_retry_service=None):
        self.storage = storage
        self.journal = journal
        self.automation_gate = automation_gate
        self.auto_safe_apply_service = auto_safe_apply_service
        self.auto_verification_service = auto_verification_service
        self.context_refresh_service = context_refresh_service
        self.evaluator_service = evaluator_service
        self.failure_stop_service = AtlasFailureStopService(journal=journal)
        self.bounded_retry_service = bounded_retry_service
        self.supervised_status_service = AtlasMultiItemSupervisedStatusService(storage=storage, journal=journal, supervised_item_status_service=AtlasSupervisedItemStatusService(storage=storage, journal=journal))

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
            self.emit("item_selected", request, autopilot_run_id, item_id=item_id, item_index=idx, status="started")
            target_files = list(getattr(item, "target_files", []) or [])
            item_md = item.metadata or {}
            precheck = self._check_eligibility(request, policy, item, target_files=target_files, changed_total=changed_total)
            planned_steps = precheck.pop("planned_steps")
            if precheck.get("status") != "eligible":
                status = "blocked" if precheck.get("reason") == "automation_gate_blocked" else "skipped"
                reason = precheck.get("reason", "ineligible")
                if reason == "automation_gate_blocked" and precheck.get("gate_reason"):
                    reason = f"{reason}:{precheck.get('gate_reason')}"
                result = AtlasAutopilotItemResult(item_id=item_id, status=status, reason=reason, metadata={"planned_steps": planned_steps})
                out.item_results.append(result); out.processed_count += 1
                out.blocked_count += 1 if status == "blocked" else 0
                out.skipped_count += 1 if status == "skipped" else 0
                self.emit("item_blocked" if status == "blocked" else "item_skipped", request, autopilot_run_id, item_id=item_id, item_index=idx, status=status, reason=result.reason)
                continue
            if request.dry_run or policy.policy_id == "dry_run_multi_item_v1":
                out.item_results.append(AtlasAutopilotItemResult(item_id=item_id, status="dry_run", reason="eligible", metadata={"planned_steps": planned_steps})); out.processed_count += 1; continue
            result = AtlasAutopilotItemResult(item_id=item_id, status="failed")
            result.metadata = {"planned_steps": planned_steps}
            try:
                if request.include_context_refresh:
                    ctx = self.context_refresh_service.refresh(AtlasContextRefreshRequest(pool_id=pool.pool_id, item_id=item_id, run_id=run_id, trigger="pre_safe_apply", workspace_id=request.workspace_id, project_path=self.resolve_project_path(request, pool, item), changed_files=target_files, policy_id=request.context_policy_id, include_local_tools=True, include_nexus_search=False, include_deep_research=False))
                    result.context_bundle_id = ctx.bundle_id
                    self.emit("multi_item_autopilot_context_refresh_completed", request, autopilot_run_id, item_id=item_id, item_index=idx, status=ctx.status, context_bundle_id=ctx.bundle_id)
                    if ctx.status in {"blocked", "failed"} and policy.require_context_refresh:
                        result.status, result.reason = "blocked", "context_refresh_failed"
                if result.status != "blocked":
                    safe = self.auto_safe_apply_service.execute_one(AtlasAutoSafeApplyRequest(pool_id=pool.pool_id, item_id=item_id, run_id=run_id, workspace_id=request.workspace_id))
                    result.safe_apply_result = safe.model_dump()
                    self.emit("multi_item_autopilot_safe_apply_completed", request, autopilot_run_id, item_id=item_id, item_index=idx, status=safe.status)
                    if safe.status != "applied":
                        result.status, result.reason = "failed", "safe_apply_not_applied"
                if result.status not in {"blocked", "failed"}:
                    if changed_total + len(target_files) > min(request.max_changed_files_total, policy.max_changed_files_total):
                        result.status, result.reason = "stopped", "max_changed_files_total_exceeded_pre_apply"
                    else:
                        vr = self.auto_verification_service.run_after_auto_safe_apply(AtlasAutoVerificationRequest(pool_id=pool.pool_id, item_id=item_id, run_id=run_id))
                        result.verification_result = vr.model_dump()
                        self.emit("multi_item_autopilot_verification_completed", request, autopilot_run_id, item_id=item_id, item_index=idx, status=vr.status)
                        if vr.status == "failed":
                            result.failure_stop_suggestion = self.failure_stop_service.build_for_verification_failure(pool, item, run_id, vr.model_dump()).model_dump()
                        if request.include_bounded_retry and self.bounded_retry_service and vr.status != "passed" and result.failure_stop_suggestion:
                            rr = self.bounded_retry_service.run(AtlasBoundedRetryRequest(pool_id=pool.pool_id, item_id=item_id, run_id=run_id, workspace_id=request.workspace_id, project_path=self.resolve_project_path(request, pool, item), policy_id=request.retry_policy_id, context_policy_id=request.context_policy_id, evaluator_policy_id=request.evaluator_policy_id, verification_result=vr.model_dump(), safe_apply_result=result.safe_apply_result, failure_stop_suggestion=result.failure_stop_suggestion, changed_files=target_files, max_attempts=request.max_retry_attempts_per_item))
                            result.metadata["bounded_retry_result"] = rr.model_dump()
                            if rr.status == "recovered":
                                result.status = "completed"
                                result.reason = "bounded_retry_recovered"
                                recovered_vr = {"status": "passed", "recovered_by_bounded_retry": True, "retry_run_id": rr.retry_run_id, "final_verification_status": rr.final_verification_status, "attempt_count": rr.attempt_count}
                                result.verification_result = recovered_vr
                                vr = type("V", (), {"status": "passed", "model_dump": lambda self: recovered_vr})()
                        if request.include_evaluator and vr.status in {"passed", "failed"}:
                            ev = self.evaluator_service.evaluate(AtlasEvaluatorRequest(pool_id=pool.pool_id, item_id=item_id, run_id=run_id, trigger="verification_failure" if vr.status == "failed" else "post_verification", context_bundle_id=result.context_bundle_id, use_latest_context_bundle=False, project_path=self.resolve_project_path(request, pool, item), changed_files=target_files, verification_result=vr.model_dump(), safe_apply_result=result.safe_apply_result, failure_stop_suggestion=result.failure_stop_suggestion, policy_id=request.evaluator_policy_id, metadata={"autopilot_run_id": autopilot_run_id, "item_index": idx}))
                            result.evaluator_result_id = str((ev.metadata or {}).get("eval_id") or "")
                            result.evaluator_decision = ev.decision.model_dump()
                        if vr.status in {"blocked", "skipped"}:
                            result.status, result.reason = "blocked", f"verification_{vr.status}"
                        elif vr.status == "failed":
                            result.status, result.reason = "failed", "verification_failed"
                        else:
                            result.status = "completed"
            except Exception as exc:
                em = str(exc)
                if "context" in em:
                    result.reason = "context_refresh_exception"
                elif "verification" in em:
                    result.reason = "verification_exception"
                elif "evaluator" in em:
                    result.reason = "evaluator_exception"
                else:
                    result.reason = "safe_apply_exception"
                result.status = "failed"
                result.errors.append(em)
                self.emit("item_failed", request, autopilot_run_id, item_id=item_id, item_index=idx, status="failed", reason=result.reason)
            decision = str((result.evaluator_decision or {}).get("decision") or "")
            result.changed_files = list((result.safe_apply_result.get("changed_files") if result.safe_apply_result else []) or [])
            changed_total += len(result.changed_files)
            if changed_total > min(request.max_changed_files_total, policy.max_changed_files_total):
                result.status, result.reason = "stopped", "max_changed_files_total_exceeded"; out.status = "stopped"; out.stop_reason = result.reason
            elif result.status == "failed":
                out.status, out.stop_reason = "stopped", result.reason
            elif result.status == "blocked":
                out.status, out.stop_reason = "stopped", result.reason
            elif decision in set(policy.stop_decisions) and (decision != "manual_required" or request.stop_on_manual_required) and (decision != "revise" or request.stop_on_revise):
                result.status, result.reason = "stopped", f"evaluator_{decision}"; out.status = "stopped"; out.stop_reason = result.reason
            elif result.status == "":
                result.status = "completed"
            out.item_results.append(result); out.processed_count += 1
            out.completed_count += 1 if result.status == "completed" else 0
            out.failed_count += 1 if result.status == "failed" else 0
            out.blocked_count += 1 if result.status == "blocked" else 0
            if out.failed_count >= min(request.max_failures, policy.max_failures):
                out.status, out.stop_reason = "stopped", "max_failures_reached"
            if out.status in {"stopped", "failed"}:
                break
        try:
            ss = self.supervised_status_service.build_status(AtlasMultiItemSupervisedStatusRequest(pool_id=request.pool_id, run_id=request.run_id, workspace_id=request.workspace_id, project_path=request.project_path, item_ids=ids, dry_run=True, refresh_item_status=False, update_item_status=False, update_metadata=False))
            out.metadata.update({"supervised_status_integrated": True, "multi_status_run_id": ss.multi_status_run_id, "next_item_id": (ss.next_item.item_id if ss.next_item else ""), "next_action": (ss.next_item.next_action if ss.next_item else ""), "counts": ss.counts, "queue_only": True, "next_action_executed": False, "supervised_status_summary": ss.model_dump()})
        except Exception as ex:
            out.warnings.append(f"supervised_status_integration_failed:{ex}")
        if out.status == "completed" and out.completed_count == 0 and out.blocked_count > 0:
            out.status = "blocked"
        if out.status == "stopped" and out.completed_count > 0:
            out.status = "partial"
        self.save_result(out)
        self.emit("completed" if out.status in {"completed", "partial"} else "failed" if out.status == "failed" else "stopped", request, autopilot_run_id, status=out.status)
        return out

    def resolve_project_path(self, request, pool, item):
        return str(request.project_path or getattr(pool, "project_path", "") or getattr(item, "project_path", "") or "")

    def _check_eligibility(self, request, policy, item, *, target_files, changed_total):
        planned_steps = ["context_refresh", "safe_apply", "verification", "evaluator"]
        if not self.resolve_project_path(request, self.storage.load_pool(request.pool_id), item):
            return {"status": "ineligible", "reason": "project_path_missing", "planned_steps": planned_steps}
        if request.require_approval and str(((item.metadata or {}).get("approval") or {}).get("decision") or "").lower() != "approved":
            return {"status": "ineligible", "reason": "approval_required", "planned_steps": planned_steps}
        if str(getattr(item, "risk_level", "")).lower() not in set(policy.allowed_risk_levels):
            return {"status": "ineligible", "reason": "risk_not_allowed", "planned_steps": planned_steps}
        if str(getattr(item, "status", "")).lower() == "completed":
            return {"status": "ineligible", "reason": "already_completed", "planned_steps": planned_steps}
        if not target_files:
            return {"status": "ineligible", "reason": "missing_target_files", "planned_steps": planned_steps}
        md = item.metadata or {}
        if not ((md.get("patch") or "") or (md.get("content") or "") or ((md.get("safe_apply") or {}).get("patch") or "")):
            return {"status": "ineligible", "reason": "missing_patch_or_content", "planned_steps": planned_steps}
        if (changed_total + len(target_files)) > min(request.max_changed_files_total, policy.max_changed_files_total):
            return {"status": "ineligible", "reason": "budget_exceeded", "planned_steps": planned_steps}
        action_type = str(md.get("action_type") or "patch")
        if action_type not in {"patch", "write"}:
            return {"status": "ineligible", "reason": "unsupported_action_type", "planned_steps": planned_steps}
        preset = atlas_auto_policy_presets().get("guarded_low_risk")
        if preset is not None:
            decision = self.automation_gate.decide_pre_safe_apply(self.storage.load_pool(request.pool_id), item, preset)
            if str(getattr(decision, "decision", "")).lower() in {"block", "require_manual"}:
                reason = str((getattr(decision, "reasons", []) or ["automation_gate_blocked"])[0])
                return {"status": "ineligible", "reason": "automation_gate_blocked", "planned_steps": planned_steps, "gate_reason": reason}
        return {"status": "eligible", "planned_steps": planned_steps}

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
            lines += [f"- item_id: {r.item_id}", f"  - status: {r.status}", f"  - reason: {r.reason}", f"  - context_bundle_id: {r.context_bundle_id}", f"  - evaluator_result_id: {r.evaluator_result_id}", f"  - evaluator_decision.decision: {(r.evaluator_decision or {}).get('decision','')}", f"  - verification_result.status: {(r.verification_result or {}).get('status','')}", f"  - verification_result.recovered_by_bounded_retry: {(r.verification_result or {}).get('recovered_by_bounded_retry', False)}", f"  - safe_apply_result.status: {(r.safe_apply_result or {}).get('status','')}"]
        lines += ["", "## Warnings"] + ([f"- {w}" for w in result.warnings] or ["- (none)"]) + ["", "## Errors"] + ([f"- {e}" for e in result.errors] or ["- (none)"])
        (root / f"{result.autopilot_run_id}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def emit(self, event_type, request, autopilot_run_id, **kw):
        if not request.run_id:
            return
        self.journal.append_event(request.pool_id, request.run_id, {"event_type": event_type, "pool_id": request.pool_id, "run_id": request.run_id, "autopilot_run_id": autopilot_run_id, "created_at": datetime.now(timezone.utc).isoformat(), **kw})
