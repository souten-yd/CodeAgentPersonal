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
from agent.atlas_file_safe_apply_executor import normalize_safe_apply_action_type
from agent.atlas_llm_evaluator_schema import AtlasEvaluatorRequest
from agent.atlas_multi_item_autopilot_policies import get_multi_item_policy
from agent.atlas_multi_item_supervised_status_schema import AtlasMultiItemSupervisedStatusRequest
from agent.atlas_multi_item_supervised_status_service import AtlasMultiItemSupervisedStatusService
from agent.atlas_plan_item_file_changes import has_file_change_content, normalize_plan_item_file_changes
from agent.atlas_self_correction_schema import AtlasSelfCorrectionRequest
from agent.atlas_supervised_item_status_service import AtlasSupervisedItemStatusService
from agent.atlas_multi_item_autopilot_schema import (
    AtlasAutopilotItemResult,
    AtlasMultiItemAutopilotRequest,
    AtlasMultiItemAutopilotResult,
)
from agent.atlas_run_quality_rollup import compute_run_quality_rollup


class AtlasMultiItemAutopilotService:
    def __init__(self, *, storage, journal, automation_gate, auto_safe_apply_service, auto_verification_service, context_refresh_service, evaluator_service, bounded_retry_service=None, self_correction_service=None, harness_provisioner=None, correction_router_service=None):
        self.storage = storage
        self.journal = journal
        self.automation_gate = automation_gate
        self.auto_safe_apply_service = auto_safe_apply_service
        self.auto_verification_service = auto_verification_service
        self.context_refresh_service = context_refresh_service
        self.evaluator_service = evaluator_service
        self.failure_stop_service = AtlasFailureStopService(journal=journal)
        self.bounded_retry_service = bounded_retry_service
        self.self_correction_service = self_correction_service
        self.harness_provisioner = harness_provisioner
        self.correction_router_service = correction_router_service
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
            norm = normalize_plan_item_file_changes(item)
            if norm.get("changed"):
                self.storage.save_pool(pool)
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
                    preset_id = "full_auto" if policy.policy_id == "full_auto_multi_item_v1" else "guarded_low_risk"
                    safe = self.auto_safe_apply_service.execute_one(AtlasAutoSafeApplyRequest(pool_id=pool.pool_id, item_id=item_id, run_id=run_id, workspace_id=request.workspace_id, preset_id=preset_id))
                    result.safe_apply_result = safe.model_dump()
                    self.emit("multi_item_autopilot_safe_apply_completed", request, autopilot_run_id, item_id=item_id, item_index=idx, status=safe.status)
                    if safe.status != "applied":
                        result.status, result.reason = "failed", "safe_apply_not_applied"
                    else:
                        # Clear the pessimistic "failed" default so the verification stage runs.
                        # (Previously this path was never reached because items were skipped at
                        # eligibility / blocked for a missing executor, leaving the bug latent.)
                        result.status, result.reason = "applied", ""
                actual_changed_files = list((result.safe_apply_result or {}).get("changed_files") or [])
                actual_file_results = list(
                    ((result.safe_apply_result or {}).get("safe_apply_result") or {}).get("file_results")
                    or ((result.safe_apply_result or {}).get("metadata") or {}).get("file_results")
                    or []
                )
                if result.status not in {"blocked", "failed"}:
                    if changed_total + len(actual_changed_files) > min(request.max_changed_files_total, policy.max_changed_files_total):
                        result.status, result.reason = "stopped", "max_changed_files_total_exceeded_pre_apply"
                    else:
                        vr = self.auto_verification_service.run_after_auto_safe_apply(AtlasAutoVerificationRequest(pool_id=pool.pool_id, item_id=item_id, run_id=run_id))
                        result.verification_result = vr.model_dump()
                        self.emit("multi_item_autopilot_verification_completed", request, autopilot_run_id, item_id=item_id, item_index=idx, status=vr.status)
                        # Harness auto-provisioning: if verification could not run because pytest is not
                        # installed, install it once and re-verify (see missing dep -> install -> re-run)
                        # rather than reporting a success we never checked. Best-effort: if the install
                        # fails, the terminal handling below records an honest "unverified" status.
                        if (request.include_harness_provisioning and self.harness_provisioner
                                and any(w in (getattr(vr, "warnings", []) or []) for w in ("pytest_not_installed", "test_harness_unavailable"))):
                            prov = self.harness_provisioner.ensure_pytest(project_path=self.resolve_project_path(request, pool, item))
                            result.metadata["harness_provisioning"] = prov
                            self.emit("multi_item_autopilot_harness_provisioning", request, autopilot_run_id, item_id=item_id, item_index=idx, status=str(prov.get("status") or ""))
                            if prov.get("status") in {"installed", "already_present"}:
                                vr = self.auto_verification_service.run_after_auto_safe_apply(AtlasAutoVerificationRequest(pool_id=pool.pool_id, item_id=item_id, run_id=run_id))
                                result.verification_result = vr.model_dump()
                                self.emit("multi_item_autopilot_verification_completed", request, autopilot_run_id, item_id=item_id, item_index=idx, status=vr.status)
                        if vr.status == "failed":
                            result.failure_stop_suggestion = self.failure_stop_service.build_for_verification_failure(pool, item, run_id, vr.model_dump()).model_dump()
                        if request.include_bounded_retry and self.bounded_retry_service and vr.status != "passed" and result.failure_stop_suggestion:
                            rr = self.bounded_retry_service.run(AtlasBoundedRetryRequest(pool_id=pool.pool_id, item_id=item_id, run_id=run_id, workspace_id=request.workspace_id, project_path=self.resolve_project_path(request, pool, item), policy_id=request.retry_policy_id, context_policy_id=request.context_policy_id, evaluator_policy_id=request.evaluator_policy_id, verification_result=vr.model_dump(), safe_apply_result=result.safe_apply_result, failure_stop_suggestion=result.failure_stop_suggestion, changed_files=actual_changed_files, max_attempts=request.max_retry_attempts_per_item))
                            result.metadata["bounded_retry_result"] = rr.model_dump()
                            if rr.status == "recovered":
                                result.status = "completed"
                                result.reason = "bounded_retry_recovered"
                                recovered_vr = {"status": "passed", "recovered_by_bounded_retry": True, "retry_run_id": rr.retry_run_id, "final_verification_status": rr.final_verification_status, "attempt_count": rr.attempt_count}
                                result.verification_result = recovered_vr
                                vr = type("V", (), {"status": "passed", "model_dump": lambda self: recovered_vr})()
                        # Self-correction: verification failed and content was applied -> feed the failing
                        # test/compile output back to the patch generator, re-apply, re-verify (bounded,
                        # low/medium risk only). This is the generate->verify->fix loop.
                        if request.include_self_correction and self.self_correction_service and vr.status == "failed":
                            sc_request = AtlasSelfCorrectionRequest(pool_id=pool.pool_id, item_id=item_id, run_id=run_id, workspace_id=request.workspace_id, project_path=self.resolve_project_path(request, pool, item), verification_result=vr.model_dump(), changed_files=actual_changed_files, file_results=actual_file_results, max_attempts=request.self_correction_max_attempts, risk_levels=request.self_correction_risk_levels)
                            # Route the failure to the right artifact (code vs test) when enabled; the
                            # router internally falls back to plain self-correction on the failing item.
                            if request.include_correction_routing and self.correction_router_service:
                                sc = self.correction_router_service.run(sc_request)
                            else:
                                sc = self.self_correction_service.run(sc_request)
                            result.metadata["self_correction_result"] = sc.model_dump()
                            # Surface *why* the repair loop didn't run (e.g. the item's risk level
                            # is above the auto-reapply threshold) so the stop is explained in the
                            # UI instead of looking like a silent halt.
                            if sc.status == "skipped" and str(sc.reason or "").startswith("risk_level_not_auto_reapplyable"):
                                if sc.reason not in result.warnings:
                                    result.warnings.append(sc.reason)
                            if sc.status == "recovered":
                                result.status = "completed"
                                result.reason = "self_correction_recovered"
                                if sc.changed_files:
                                    result.safe_apply_result = {**(result.safe_apply_result or {}), "changed_files": sc.changed_files}
                                recovered_vr = {"status": "passed", "recovered_by_self_correction": True, "final_verification_status": sc.final_verification_status, "attempt_count": sc.attempts}
                                result.verification_result = recovered_vr
                                vr = type("V", (), {"status": "passed", "model_dump": lambda self: recovered_vr})()
                        if request.include_evaluator and vr.status in {"passed", "failed"}:
                            ev = self.evaluator_service.evaluate(AtlasEvaluatorRequest(pool_id=pool.pool_id, item_id=item_id, run_id=run_id, trigger="verification_failure" if vr.status == "failed" else "post_verification", context_bundle_id=result.context_bundle_id, use_latest_context_bundle=False, project_path=self.resolve_project_path(request, pool, item), changed_files=actual_changed_files, verification_result=vr.model_dump(), safe_apply_result=result.safe_apply_result, failure_stop_suggestion=result.failure_stop_suggestion, policy_id=request.evaluator_policy_id, metadata={"autopilot_run_id": autopilot_run_id, "item_index": idx}))
                            result.evaluator_result_id = str((ev.metadata or {}).get("eval_id") or "")
                            result.evaluator_decision = ev.decision.model_dump()
                        vr_warnings = list(getattr(vr, "warnings", []) or [])
                        # Surface verification warnings on the item so the user can see *why* a test
                        # could not be run (e.g. pytest_not_installed) instead of a silent caveat.
                        for w in vr_warnings:
                            if w not in result.warnings:
                                result.warnings.append(w)
                        # No verification command / no tests configured means there was genuinely
                        # nothing to verify — the change was applied successfully, so report completed
                        # with a caveat reason.
                        no_verification_configured = any(
                            w in vr_warnings for w in ("verification_command_missing", "no_test_commands")
                        )
                        # The harness still could not run after the provisioning attempt above (e.g.
                        # pytest could not be installed because there is no network). Do NOT claim
                        # success we never verified: report an honest "applied but unverified" block so
                        # the user knows to install the harness, instead of a misleading completed.
                        harness_unavailable = any(
                            w in vr_warnings for w in ("test_harness_unavailable", "pytest_not_installed")
                        )
                        if vr.status in {"blocked", "skipped"} and no_verification_configured:
                            result.status, result.reason = "applied_no_verification", "applied_no_verification"
                        elif vr.status == "blocked" and harness_unavailable:
                            result.status, result.reason = "blocked", "verification_unavailable_harness_missing"
                        elif vr.status == "blocked":
                            result.status, result.reason = "blocked", "verification_blocked"
                        elif vr.status == "skipped":
                            result.status, result.reason = "completed", "verification_skipped"
                        elif vr.status == "failed":
                            # Surface the precise reason (e.g. browser_smoke_failed:js_error,
                            # visual_missing:*) alongside the generic marker. The
                            # ``verification_failed`` prefix is preserved so existing
                            # startswith/equality consumers still match.
                            _primary = primary_verification_reason(vr_warnings)
                            result.status = "failed"
                            result.reason = f"verification_failed:{_primary}" if _primary else "verification_failed"
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
            out.applied_no_verification_count += 1 if result.status == "applied_no_verification" else 0
            out.failed_count += 1 if result.status == "failed" else 0
            out.blocked_count += 1 if result.status == "blocked" else 0
            if out.failed_count >= min(request.max_failures, policy.max_failures):
                out.status, out.stop_reason = "stopped", "max_failures_reached"
            if out.status in {"stopped", "failed"}:
                break
        try:
            ss = self.supervised_status_service.build_status(AtlasMultiItemSupervisedStatusRequest(pool_id=request.pool_id, run_id=request.run_id, workspace_id=request.workspace_id, project_path=request.project_path, item_ids=ids, dry_run=True, refresh_item_status=False, update_item_status=False, update_metadata=False))
            out.metadata.update({"supervised_status_integrated": True, "multi_status_run_id": ss.multi_status_run_id, "next_item_id": (ss.next_item.item_id if ss.next_item else ""), "next_action": (ss.next_item.next_action if ss.next_item else ""), "counts": ss.counts, "queue_only": True, "next_action_executed": False, "supervised_status_summary": ss.model_dump(), "next_action_orchestrator_available": True, "latest_next_action_contract_path": "", "next_action_execution_supported": False})
        except Exception as ex:
            out.warnings.append(f"supervised_status_integration_failed:{ex}")
        if out.status == "completed" and out.completed_count == 0 and out.blocked_count > 0:
            out.status = "blocked"
        if out.status == "stopped" and out.completed_count > 0:
            out.status = "partial"
        # ── Final-status quality rollup (PR-8d): requirement coverage, integration,
        # placeholder, and repair checks. A would-be-success run is degraded to "partial"
        # when concrete defects are found (disconnected user-facing module, placeholder-only
        # implementation, test-only repair plan, or zero implementation evidence).
        try:
            final_pool = self.storage.load_pool(request.pool_id)
            rollup = compute_run_quality_rollup(final_pool, out.item_results, project_path=request.project_path or getattr(final_pool, "project_path", ""))
            out.metadata["quality_rollup"] = rollup
            for w in rollup.get("warnings", []):
                if w not in out.warnings:
                    out.warnings.append(w)
            for w in rollup.get("degrade_reasons", []):
                if w not in out.warnings:
                    out.warnings.append(w)
            if rollup.get("degraded") and out.status in {"completed"}:
                # Quality enforcement (Features): "block" elevates a degraded run (disconnected
                # module / placeholder-only / no implementation evidence) to needs_revision so it
                # is NOT reported as success; "warn" keeps the legacy partial degrade.
                _features = (getattr(final_pool, "metadata", {}) or {}).get("automation_features") or {}
                _enforce = str(_features.get("quality_gate_enforcement") or "warn").lower() == "block"
                out.status = "needs_revision" if _enforce else "partial"
                out.stop_reason = (rollup.get("degrade_reasons") or ["quality_rollup_degraded"])[0]
        except Exception as ex:  # noqa: BLE001
            out.warnings.append(f"quality_rollup_failed:{ex}")
        self.save_result(out)
        self.emit("completed" if out.status in {"completed", "partial"} else "failed" if out.status in {"failed", "needs_revision"} else "stopped", request, autopilot_run_id, status=out.status)
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
        # Content keys the file executor (AtlasFileSafeApplyExecutor._resolve_content) actually
        # reads: proposed_content / patch_proposal.proposed_content / patch / unified_diff_preview.
        # "content" is kept for back-compat with older proposals.
        patch_proposal = md.get("patch_proposal") or {}
        file_changes = md.get("file_changes") if isinstance(md.get("file_changes"), list) else []
        file_change_content = bool(file_changes) and all(isinstance(fc, dict) and has_file_change_content(fc) for fc in file_changes)
        if not (
            file_change_content
            or
            (md.get("patch") or "")
            or (md.get("content") or "")
            or (md.get("proposed_content") or "")
            or (md.get("unified_diff_preview") or "")
            or (patch_proposal.get("proposed_content") or "")
            or (patch_proposal.get("unified_diff_preview") or "")
            or ((md.get("safe_apply") or {}).get("patch") or "")
        ):
            return {"status": "ineligible", "reason": "missing_patch_or_content", "planned_steps": planned_steps}
        if (changed_total + len(target_files)) > min(request.max_changed_files_total, policy.max_changed_files_total):
            return {"status": "ineligible", "reason": "budget_exceeded", "planned_steps": planned_steps}
        # Canonical action_type is {create, update} (what the executor applies). Accept the legacy
        # {patch, write} vocabulary for back-compat; empty defaults to create (greenfield write).
        action_type = normalize_safe_apply_action_type(md.get("action_type"))
        if action_type not in {"create", "update"}:
            return {"status": "ineligible", "reason": "unsupported_action_type", "planned_steps": planned_steps}
        # Pick the gate preset to match the run policy: a policy that allows medium/high risk uses the
        # full-auto preset so the automation gate doesn't re-block what the policy already permits.
        preset_id = "full_auto" if (set(policy.allowed_risk_levels) - {"low"}) else "guarded_low_risk"
        preset = atlas_auto_policy_presets().get(preset_id)
        if preset is not None:
            decision = self.automation_gate.decide_pre_safe_apply(self.storage.load_pool(request.pool_id), item, preset)
            gate = str(getattr(decision, "decision", "")).lower()
            # A hard "block" (security/policy violation) always stops the item. A soft "require_manual"
            # (e.g. approval bookkeeping) only stops when the caller actually wants an approval gate;
            # for an opted-in full-automation run (require_approval=False) it proceeds.
            blocked = gate == "block" or (gate == "require_manual" and getattr(request, "require_approval", True))
            if blocked:
                reason = str((getattr(decision, "reasons", []) or ["automation_gate_blocked"])[0])
                return {"status": "ineligible", "reason": "automation_gate_blocked", "planned_steps": planned_steps, "gate_reason": reason}
        return {"status": "eligible", "planned_steps": planned_steps}

    def save_result(self, result: AtlasMultiItemAutopilotResult):
        validate_relative_path(result.pool_id)
        root = Path("ca_data") / "atlas" / "multi_item_autopilot" / result.pool_id
        root.mkdir(parents=True, exist_ok=True)
        (root / f"{result.autopilot_run_id}.json").write_text(json.dumps(result.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        lines = ["# Multi-item Autopilot Run", "", "## Summary"]
        for k in ["autopilot_run_id", "pool_id", "run_id", "policy_id", "status", "processed_count", "completed_count", "applied_no_verification_count", "failed_count", "stop_reason"]:
            lines.append(f"- {k}: {getattr(result, k)}")
        lines += ["", "## Item Results"]
        for r in result.item_results:
            verify_level = _verify_level_for_item(r)
            verify_note = " (適用のみ・実行検証なし)" if r.status == "applied_no_verification" else ""
            item_warnings = ", ".join(str(w) for w in (r.warnings or [])) or "(none)"
            browser_smoke = (((r.verification_result or {}).get("metadata") or {}).get("browser_smoke") or {})
            console_errors = "; ".join(str(e) for e in (browser_smoke.get("console_errors") or [])[:5]) if isinstance(browser_smoke, dict) else ""
            lines += [f"- item_id: {r.item_id}", f"  - status: {r.status}{verify_note}", f"  - verify_level: {verify_level}", f"  - reason: {r.reason}", f"  - verification_warnings: {item_warnings}", f"  - browser_smoke.console_errors: {console_errors or '(none)'}", f"  - context_bundle_id: {r.context_bundle_id}", f"  - evaluator_result_id: {r.evaluator_result_id}", f"  - evaluator_decision.decision: {(r.evaluator_decision or {}).get('decision','')}", f"  - verification_result.status: {(r.verification_result or {}).get('status','')}", f"  - verification_result.recovered_by_bounded_retry: {(r.verification_result or {}).get('recovered_by_bounded_retry', False)}", f"  - safe_apply_result.status: {(r.safe_apply_result or {}).get('status','')}"]
        rollup = (result.metadata or {}).get("quality_rollup") or {}
        if rollup:
            coverage = rollup.get("requirement_coverage", {})
            lines += [
                "", "## Quality Rollup",
                f"- requirement_coverage.total: {coverage.get('total', 0)}",
                f"- requirement_coverage.by_status: {coverage.get('by_status', {})}",
                f"- requirement_coverage.success_eligible: {coverage.get('success_eligible', True)}",
                f"- integration_warnings: {len(rollup.get('integration_warnings', []))}",
                f"- placeholder_warnings: {len(rollup.get('placeholder_warnings', []))}",
                f"- repair_warning: {rollup.get('repair_warning', '') or '(none)'}",
                f"- degraded: {rollup.get('degraded', False)}",
                f"- degrade_reasons: {', '.join(rollup.get('degrade_reasons', [])) or '(none)'}",
            ]
        lines += ["", "## Warnings"] + ([f"- {w}" for w in result.warnings] or ["- (none)"]) + ["", "## Errors"] + ([f"- {e}" for e in result.errors] or ["- (none)"])
        (root / f"{result.autopilot_run_id}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def emit(self, event_type, request, autopilot_run_id, **kw):
        if not request.run_id:
            return
        self.journal.append_event(request.pool_id, request.run_id, {"event_type": event_type, "pool_id": request.pool_id, "run_id": request.run_id, "autopilot_run_id": autopilot_run_id, "created_at": datetime.now(timezone.utc).isoformat(), **kw})


# Ordered by how actionable the marker is. The dominant precise reason is appended to the
# generic ``verification_failed`` so the UI / recovery surfaces *why* (e.g. a browser JS error
# or a missing visual signal) instead of an opaque stop. Soft markers
# (``browser_smoke_warning:*``) and pass markers are intentionally excluded — they are not
# failures.
_VERIFICATION_REASON_PRIORITY = (
    "browser_smoke_failed:",
    "visual_contract_failed",
    "visual_missing:",
    "test_harness_unavailable",
    "pytest_not_installed",
)
_NON_FAILURE_WARNINGS = ("visual_contract_passed",)


def primary_verification_reason(warnings) -> str:
    """Pick the dominant, most actionable verification-failure marker from warnings."""
    items = [str(w) for w in (warnings or [])]
    for prefix in _VERIFICATION_REASON_PRIORITY:
        for w in items:
            if w == prefix or w.startswith(prefix):
                return w
    for w in items:
        if w in _NON_FAILURE_WARNINGS or w.startswith("browser_smoke_warning"):
            continue
        return w
    return ""


def _verify_level_for_item(r) -> str:
    """Classify the highest verify level reached for a single autopilot item result.

    Reads verification metadata written by the auto-verification service:
    - explicit metadata.verify_level (visual static/browser smoke) takes precedence
    - browser_smoke_passed → runtime_smoke_checked
    - requirement coverage all verified → requirement_checked
    - plain test pass → runtime_smoke_checked
    - skipped/blocked → static_checked
    """
    status = str(r.status or "")
    vr = r.verification_result or {}
    vr_status = str(vr.get("status") or "")
    meta = vr.get("metadata") or {}
    if status == "applied_no_verification":
        return "applied_only"
    if status not in {"completed"}:
        return "applied_only"
    # Requirement coverage fully verified is the strongest signal.
    coverage = meta.get("requirement_coverage") or vr.get("requirement_coverage") or {}
    if isinstance(coverage, dict) and coverage.get("all_verified"):
        return "requirement_checked"
    # A passing constrained browser smoke is a real runtime check.
    if str((meta.get("browser_smoke") or {}).get("status")) == "browser_smoke_passed":
        return "runtime_smoke_checked"
    # Explicit cap from the visual contract path (static_checked unless smoke lifted it).
    explicit = str(meta.get("verify_level") or "")
    if explicit:
        return explicit
    if vr_status == "passed":
        return "runtime_smoke_checked"
    if vr_status in {"skipped", "blocked"}:
        return "static_checked"
    return "applied_only"
