from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

from app.atlas.candidate_workspace_manager import load_candidate_workspace_plan
from app.atlas.draft_pr_creation import DraftPullRequestClient
from agent.atlas_autonomous_codegen_orchestrator_schema import (
    AtlasAutonomousCodegenProposalResult,
    AtlasAutonomousCodegenRequest,
    AtlasAutonomousCodegenResult,
)
from agent.atlas_codegen_progress import is_stop_requested, write_progress
from agent.atlas_ci_failure_repair_schema import AtlasCIFailureRepairRequest
from agent.atlas_ci_failure_repair_service import AtlasCIFailureRepairService
from agent.atlas_file_safe_apply_executor import normalize_safe_apply_action_type
from agent.atlas_multi_item_autopilot_schema import AtlasMultiItemAutopilotRequest
from agent.atlas_patch_proposal_schema import AtlasPatchProposalRequest
from agent.atlas_plan_item_file_changes import has_file_change_content, normalize_plan_item_file_changes
from agent.atlas_recovery_service import AtlasRecoveryService

# Items the full-auto profile never applies; generating a patch for them is wasted work because
# the safe-apply gate (and atlas_full_auto_gate) hard-block them downstream anyway.
_HARD_BLOCK_ACTION_TYPES = {"delete", "run_command"}
_KNOWN_PROFILES = {"review_only", "guarded_single_action", "supervised_bounded_auto", "autonomous_dev_agent"}
_AUTONOMOUS_PHASES = [
    "idle", "understanding_goal", "planning", "adversarial_review",
    "needs_scope_confirmation", "revising_plan_from_clarification",
    "waiting_for_critical_decision", "replanning_lower_impact",
    "candidate_generation", "candidate_apply", "verification",
    "failure_analysis", "bounded_repair", "final_summary", "draft_pr_preparation",
]


class AtlasAutonomousCodegenOrchestratorService:
    """Compose plan -> batch patch generation -> multi-item apply into one autonomous call.

    This adds NO new gate logic: Phase 3 delegates to AtlasMultiItemAutopilotService, which already
    inherits the workstream-1 full_auto relaxation. The safety boundary is the plan-time critique
    gate (Phase 1 stop) plus the pre-apply snapshot/rollback inside the multi-item engine.
    """

    def __init__(self, *, storage, journal, patch_proposal_service, multi_item_autopilot_service, data_root=None, draft_pr_client: DraftPullRequestClient | None = None):
        self.storage = storage
        self.journal = journal
        self.patch_proposal_service = patch_proposal_service
        self.multi_item_autopilot_service = multi_item_autopilot_service
        self.data_root = Path(data_root or getattr(journal, "root_dir", "ca_data"))
        self.draft_pr_client = draft_pr_client

    def run(self, request: AtlasAutonomousCodegenRequest) -> AtlasAutonomousCodegenResult:
        run_id = request.run_id or f"autocodegen_{uuid4().hex[:10]}"
        orchestrator_run_id = request.orchestrator_run_id or f"acg_{uuid4().hex[:10]}"
        out = AtlasAutonomousCodegenResult(
            pool_id=request.pool_id,
            run_id=run_id,
            orchestrator_run_id=orchestrator_run_id,
            status="running",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        out.metadata["phase_order"] = list(_AUTONOMOUS_PHASES)
        self._progress(request.pool_id, run_id, orchestrator_run_id, phase="understanding_goal", last_event="autonomous_codegen_started")
        self._emit("autonomous_codegen_started", request.pool_id, run_id, orchestrator_run_id, status="started")

        # ── Phase 0: load + tag the pool as full_autopilot ───────────────────────────────────
        out.phase = "understanding_goal"
        if self._stop_requested(request.pool_id, orchestrator_run_id):
            return self._stopped_result(out, request.pool_id, run_id, orchestrator_run_id)
        pool = self.storage.load_pool(request.pool_id)
        preflight = self._preflight(request, pool)
        out.metadata["preflight"] = preflight
        out.metadata["workspace_evidence"] = preflight.get("workspace_evidence", {})
        out.metadata["recovery_evidence"] = preflight.get("recovery_evidence", {})
        ci_failure_metadata = self._ci_failure_metadata(request, pool)
        if ci_failure_metadata:
            out.metadata.update(ci_failure_metadata)
        for warning in preflight.get("warnings", []):
            if warning not in out.warnings:
                out.warnings.append(warning)
        if preflight.get("status") == "blocked":
            out.phase = preflight.get("phase") or "understanding_goal"
            out.status = "stopped"
            out.stop_reason = preflight.get("reason") or "preflight_blocked"
            self._emit("autonomous_codegen_stopped_preflight", request.pool_id, run_id, orchestrator_run_id, status=out.status, reason=out.stop_reason)
            self.save_result(out)
            return out
        if str(getattr(pool, "automation_level", "")) != "full_autopilot":
            pool.automation_level = "full_autopilot"
            self.storage.save_pool(pool)
        if not pool.items:
            out.phase, out.status, out.stop_reason = "completed", "no_items", "pool_has_no_items"
            self._emit("autonomous_codegen_completed", request.pool_id, run_id, orchestrator_run_id, status=out.status)
            self.save_result(out)
            return out

        # ── Phase 1: safety gate (the hard boundary the user agreed to keep) ──────────────────
        out.phase = "adversarial_review"
        self._progress(request.pool_id, run_id, orchestrator_run_id, phase=out.phase, last_event="adversarial_review_started")
        if self._stop_requested(request.pool_id, orchestrator_run_id):
            return self._stopped_result(out, request.pool_id, run_id, orchestrator_run_id)
        revision_required = bool((pool.metadata or {}).get("plan_revision_required"))
        approval_required = str(getattr(pool, "status", "")).lower() == "approval_required"
        if revision_required or approval_required or str(getattr(pool, "status", "")).lower() in {"needs_scope_confirmation", "waiting_for_critical_decision"}:
            out.status = "blocked_safety_review"
            if str(getattr(pool, "status", "")).lower() == "needs_scope_confirmation":
                out.phase = "needs_scope_confirmation"
                out.stop_reason = "clarification_required"
            elif str(getattr(pool, "status", "")).lower() == "waiting_for_critical_decision":
                out.phase = "waiting_for_critical_decision"
                out.stop_reason = "critical_event_waiting_for_user_decision"
            else:
                out.stop_reason = "plan_revision_required" if revision_required else "approval_required"
            self._emit("autonomous_codegen_blocked_safety_review", request.pool_id, run_id, orchestrator_run_id, status=out.status, reason=out.stop_reason)
            self.save_result(out)
            return out

        # ── Phase 2: batch first-patch generation for items lacking content ───────────────────
        out.phase = "candidate_generation"
        self._progress(request.pool_id, run_id, orchestrator_run_id, phase=out.phase, sub_phase="patch_generation", last_event="candidate_generation_started")
        if self._stop_requested(request.pool_id, orchestrator_run_id):
            return self._stopped_result(out, request.pool_id, run_id, orchestrator_run_id)
        effective_limits = preflight.get("effective_limits") if isinstance(preflight.get("effective_limits"), dict) else {}
        effective_max_actions = int(effective_limits.get("max_actions") or request.max_actions)
        effective_max_items = int(effective_limits.get("max_items") or request.max_items)
        effective_max_runtime_seconds = int(effective_limits.get("max_runtime_seconds") or request.max_runtime_seconds)
        effective_max_changed_files_total = int(effective_limits.get("max_changed_files_total") or request.max_changed_files_total)
        requested_item_ids = request.item_ids or [i.item_id for i in pool.items]
        excluded_apply_item_ids: set[str] = set()
        if request.generate_missing_patches:
            for item_id in requested_item_ids[: max(0, min(effective_max_items, effective_max_actions))]:
                self._progress(request.pool_id, run_id, orchestrator_run_id, phase=out.phase, current_item_index=out.generated_count + out.skipped_generation_count, total_items=len(requested_item_ids), sub_phase="patch_generation", last_event="patch_generation_item_started")
                if self._stop_requested(request.pool_id, orchestrator_run_id):
                    return self._stopped_result(out, request.pool_id, run_id, orchestrator_run_id)
                pool = self.storage.load_pool(request.pool_id)  # pick up content persisted so far
                item = pool.get_item(item_id)
                if item is None:
                    excluded_apply_item_ids.add(item_id)
                    continue
                normalize_plan_item_file_changes(item)
                if self._item_has_patch_content(item):
                    out.skipped_generation_count += 1
                    continue
                if self._is_hard_blocked_item(item):
                    out.skipped_generation_count += 1
                    excluded_apply_item_ids.add(item_id)
                    out.proposal_results.append(AtlasAutonomousCodegenProposalResult(item_id=item_id, status="skipped", reason="hard_blocked_item"))
                    continue
                pres = self.patch_proposal_service.propose_for_item(
                    AtlasPatchProposalRequest(
                        pool_id=request.pool_id,
                        item_id=item_id,
                        run_id=run_id,
                        workspace_id=request.workspace_id,
                        source_type="plan_item",
                    )
                )
                available = bool((pres.metadata or {}).get("patch_content_available"))
                out.proposal_results.append(
                    AtlasAutonomousCodegenProposalResult(
                        item_id=item_id,
                        status=pres.status if available else "no_content",
                        patch_content_available=available,
                        reason="" if available else (pres.warnings[0] if pres.warnings else "patch_content_unavailable"),
                    )
                )
                if available:
                    out.generated_count += 1
                else:
                    out.skipped_generation_count += 1
                    excluded_apply_item_ids.add(item_id)
            self._emit("autonomous_codegen_patch_generation_completed", request.pool_id, run_id, orchestrator_run_id, status="completed", generated_count=out.generated_count, skipped_count=out.skipped_generation_count)

        apply_item_ids = [item_id for item_id in requested_item_ids if item_id not in excluded_apply_item_ids]
        if requested_item_ids and not apply_item_ids:
            out.phase = "final_summary"
            out.status = "no_content"
            out.stop_reason = "no_patch_content"
            out.metadata.update(
                {
                    "preflight": preflight,
                    "processed_count": 0,
                    "completed_count": 0,
                    "failed_count": 0,
                    "blocked_count": len(excluded_apply_item_ids),
                    "changed_files": [],
                    "no_content_item_ids": sorted(excluded_apply_item_ids),
                    "draft_pr_readiness": {
                        "ready": False,
                        "reason": "no_verified_patch_content",
                        "direct_merge_enabled": False,
                        "remote_git_push_enabled": False,
                        "self_apply_enabled": False,
                        "stable_runtime_mutation_enabled": False,
                    },
                    "draft_pr_artifact": {"ready": False, "reason": "no_verified_patch_content"},
                }
            )
            self._emit("autonomous_codegen_completed", request.pool_id, run_id, orchestrator_run_id, status=out.status)
            self.save_result(out)
            return out

        # ── Phase 3: multi-item apply (inherits full_auto relaxation + verify/self-correct) ───
        out.phase = "candidate_apply"
        self._progress(request.pool_id, run_id, orchestrator_run_id, phase=out.phase, current_item_index=0, total_items=len(apply_item_ids), sub_phase="candidate_apply", last_event="candidate_apply_started")
        if self._stop_requested(request.pool_id, orchestrator_run_id):
            return self._stopped_result(out, request.pool_id, run_id, orchestrator_run_id)
        autopilot = self.multi_item_autopilot_service.run(
            AtlasMultiItemAutopilotRequest(
                pool_id=request.pool_id,
                run_id=run_id,
                workspace_id=request.workspace_id,
                project_path=str(preflight.get("effective_project_path") or request.project_path),
                item_ids=apply_item_ids if excluded_apply_item_ids else request.item_ids,
                policy_id=request.policy_id,
                require_approval=False,
                max_items=min(effective_max_items, effective_max_actions),
                max_runtime_seconds=effective_max_runtime_seconds,
                max_changed_files_total=effective_max_changed_files_total,
                include_context_refresh=True,
                include_evaluator=True,
                include_bounded_retry=True,
                include_self_correction=True,
                include_correction_routing=True,
                include_harness_provisioning=True,
                metadata={
                    **(request.metadata or {}),
                    "data_root": str(self.data_root),
                    "orchestrator_run_id": orchestrator_run_id,
                },
            )
        )
        out.autopilot_result = autopilot.model_dump()
        out.stop_reason = autopilot.stop_reason
        for w in autopilot.warnings:
            if w not in out.warnings:
                out.warnings.append(w)
        repair_evidence = self._build_repairable_verification_evidence(request, autopilot)

        # ── Phase 4: aggregate ────────────────────────────────────────────────────────────────
        out.phase = "final_summary"
        self._progress(request.pool_id, run_id, orchestrator_run_id, phase=out.phase, sub_phase="final_summary", last_event="final_summary_started")
        out.status = autopilot.status or "completed"
        if repair_evidence:
            out.phase = "failure_analysis"
            out.stop_reason = out.stop_reason or "repairable_verification_failed"
        changed_files = self._changed_files_from_autopilot(autopilot)
        recovery_evidence = dict(out.metadata.get("recovery_evidence") or {})
        recovery_evidence["changed_files"] = changed_files
        recovery_evidence["restore_available"] = bool(
            recovery_evidence.get("snapshot_manifest_path")
            or (recovery_evidence.get("references") or {}).get("restore_plan_ref")
            or (recovery_evidence.get("references") or {}).get("rollback_plan_ref")
        )
        out.metadata["recovery_evidence"] = recovery_evidence
        out.metadata.update(
            {
                "autopilot_run_id": autopilot.autopilot_run_id,
                "processed_count": autopilot.processed_count,
                "completed_count": autopilot.completed_count,
                "failed_count": autopilot.failed_count,
                "blocked_count": autopilot.blocked_count,
                "changed_files": changed_files,
                "draft_pr_readiness": {
                    "ready": out.status in {"completed", "partial"},
                    "direct_merge_enabled": False,
                    "remote_git_push_enabled": False,
                    "self_apply_enabled": False,
                    "stable_runtime_mutation_enabled": False,
                },
            }
        )
        if repair_evidence:
            out.metadata.update(repair_evidence)
        self_platform_review_gate = self._self_platform_review_gate(out.metadata, self.storage.load_pool(request.pool_id))
        if self_platform_review_gate:
            out.metadata["self_platform_review_gate"] = self_platform_review_gate
        draft_pr_artifact = self._prepare_draft_pr_artifact(
            result=out,
            request=request,
            pool=self.storage.load_pool(request.pool_id),
            autopilot=autopilot,
        )
        out.metadata["draft_pr_artifact"] = draft_pr_artifact
        artifact_readiness = (
            draft_pr_artifact.get("readiness") if isinstance(draft_pr_artifact.get("readiness"), dict) else {}
        )
        out.metadata["draft_pr_readiness"] = {
            **(out.metadata.get("draft_pr_readiness") or {}),
            **artifact_readiness,
            "ready": bool(draft_pr_artifact.get("ready")),
            "artifact_path": str(draft_pr_artifact.get("artifact_path") or ""),
            "body_path": str(draft_pr_artifact.get("body_path") or ""),
            "draft_pr_created": bool((draft_pr_artifact.get("creation_result") or {}).get("draft_pr_created")),
            "draft_pr_url": str((draft_pr_artifact.get("creation_result") or {}).get("draft_pr_url") or ""),
            "direct_merge_enabled": False,
            "remote_git_push_enabled": False,
            "self_apply_enabled": False,
            "stable_runtime_mutation_enabled": False,
        }
        out.metadata["auto_merge_readiness"] = self._auto_merge_readiness(out.metadata, autopilot, request)
        self._emit("autonomous_codegen_completed", request.pool_id, run_id, orchestrator_run_id, status=out.status)
        self._progress(request.pool_id, run_id, orchestrator_run_id, phase=out.phase, status=out.status, sub_phase="", last_event="autonomous_codegen_completed", processed_count=out.metadata.get("processed_count", 0), completed_count=out.metadata.get("completed_count", 0), failed_count=out.metadata.get("failed_count", 0), blocked_count=out.metadata.get("blocked_count", 0))
        self.save_result(out)
        return out

    def _progress(self, pool_id: str, run_id: str, orchestrator_run_id: str, **patch) -> None:
        write_progress(
            self.data_root,
            pool_id,
            orchestrator_run_id,
            {"pool_id": pool_id, "run_id": run_id, "orchestrator_run_id": orchestrator_run_id, **patch},
        )

    def _stop_requested(self, pool_id: str, orchestrator_run_id: str) -> bool:
        return is_stop_requested(self.data_root, pool_id, orchestrator_run_id)

    def _stopped_result(self, out: AtlasAutonomousCodegenResult, pool_id: str, run_id: str, orchestrator_run_id: str) -> AtlasAutonomousCodegenResult:
        out.status = "stopped"
        out.stop_reason = "user_stop_requested"
        out.phase = out.phase or "final_summary"
        self._emit("autonomous_codegen_stopped", pool_id, run_id, orchestrator_run_id, status=out.status, reason=out.stop_reason)
        self._progress(pool_id, run_id, orchestrator_run_id, phase=out.phase, status=out.status, last_event="autonomous_codegen_stopped", stop_requested=True, stop_reason=out.stop_reason)
        self.save_result(out)
        return out

    def _ci_failure_metadata(self, request: AtlasAutonomousCodegenRequest, pool: AtlasPlanPool) -> dict[str, Any]:
        metadata = request.metadata or {}
        supplied = metadata.get("ci_failure_evidence") if isinstance(metadata.get("ci_failure_evidence"), dict) else {}
        log_text = str(metadata.get("ci_failure_log") or supplied.get("log_text") or supplied.get("log_excerpt") or "")
        failing_tests = list(metadata.get("ci_failing_tests") or supplied.get("failing_test_names") or [])
        affected_files = list(metadata.get("ci_affected_files") or supplied.get("affected_files") or [])
        if not (log_text.strip() or failing_tests or affected_files):
            return {}
        plan_items = [item.model_dump() for item in getattr(pool, "items", []) or []]
        return AtlasCIFailureRepairService().build(
            AtlasCIFailureRepairRequest(
                source=str(supplied.get("source") or metadata.get("ci_failure_source") or "manual"),
                run_id=str(supplied.get("run_id") or metadata.get("ci_run_id") or ""),
                job_id=str(supplied.get("job_id") or metadata.get("ci_job_id") or ""),
                failing_command=str(supplied.get("failing_command") or metadata.get("ci_failing_command") or ""),
                log_text=log_text,
                failing_test_names=[str(item) for item in failing_tests],
                affected_files=[str(path) for path in affected_files],
                allowed_paths=list(request.allowed_paths or []),
                plan_items=plan_items,
            )
        )

    def _preflight(self, request: AtlasAutonomousCodegenRequest, pool: AtlasPlanPool) -> dict:
        project_path = str(request.project_path or getattr(pool, "project_path", "") or "").strip()
        if not project_path:
            return {"status": "blocked", "phase": "understanding_goal", "reason": "missing_project_path"}
        profile = str(request.selected_profile or "review_only")
        warnings: list[str] = []
        envelope = request.envelope or {}
        workspace_evidence = self._workspace_evidence(request, pool, project_path, profile)
        recovery_evidence = self._recovery_evidence(request, pool)
        for warning in workspace_evidence.get("warnings", []):
            if warning not in warnings:
                warnings.append(warning)
        for warning in recovery_evidence.get("warnings", []):
            if warning not in warnings:
                warnings.append(warning)
        if profile not in _KNOWN_PROFILES:
            warnings.append("unknown_profile_fell_back_to_review_only")
            profile = "review_only"
            return {
                "status": "blocked",
                "phase": "understanding_goal",
                "reason": "unknown_profile_fallback",
                "normalized_profile": profile,
                "warnings": warnings,
                "workspace_evidence": workspace_evidence,
                "recovery_evidence": recovery_evidence,
            }
        if request.self_improvement and not bool((request.envelope or {}).get("strict_gate_approved")):
            return {
                "status": "blocked",
                "phase": "understanding_goal",
                "reason": "self_improvement_without_strict_gate",
                "normalized_profile": profile,
                "warnings": warnings,
                "workspace_evidence": workspace_evidence,
                "recovery_evidence": recovery_evidence,
            }
        envelope_status = str(envelope.get("status") or "").lower()
        envelope_id = str(envelope.get("envelope_id") or "")
        if profile == "autonomous_dev_agent" and not (envelope_status == "active" and envelope_id):
            return {
                "status": "blocked",
                "phase": "understanding_goal",
                "reason": "selected_profile_inactive_envelope",
                "normalized_profile": profile,
                "warnings": warnings,
                "workspace_evidence": workspace_evidence,
                "recovery_evidence": recovery_evidence,
            }
        effective_limits = self._effective_limits(request, envelope)
        if effective_limits.get("clamped") and "request_limits_clamped_to_envelope" not in warnings:
            warnings.append("request_limits_clamped_to_envelope")
        if request.allowed_verification_commands:
            return {
                "status": "blocked",
                "phase": "understanding_goal",
                "reason": "allowed_verification_commands_unsupported",
                "normalized_profile": profile,
                "warnings": warnings,
                "workspace_evidence": workspace_evidence,
                "recovery_evidence": recovery_evidence,
                "effective_limits": effective_limits,
                "allowed_verification_commands": list(request.allowed_verification_commands),
            }
        workspace_block = workspace_evidence.get("blocking_reason", "")
        if workspace_block:
            return {
                "status": "blocked",
                "phase": "understanding_goal",
                "reason": workspace_block,
                "normalized_profile": profile,
                "warnings": warnings,
                "workspace_evidence": workspace_evidence,
                "recovery_evidence": recovery_evidence,
            }
        paths = self._requested_paths(request, pool)
        self_platform_target = self._classify_self_platform_target(paths)
        if self_platform_target.get("is_self_platform") and not request.self_improvement:
            return {
                "status": "blocked",
                "phase": "understanding_goal",
                "reason": "self_platform_requires_self_improvement",
                "paths": paths,
                "warnings": warnings,
                "workspace_evidence": workspace_evidence,
                "recovery_evidence": recovery_evidence,
                "effective_limits": effective_limits,
                "self_platform_target": self_platform_target,
            }
        if self_platform_target.get("is_self_platform") and envelope_id != "pre_authorized_self_improvement_envelope":
            return {
                "status": "blocked",
                "phase": "understanding_goal",
                "reason": "self_platform_requires_self_improvement_envelope",
                "paths": paths,
                "warnings": warnings,
                "workspace_evidence": workspace_evidence,
                "recovery_evidence": recovery_evidence,
                "effective_limits": effective_limits,
                "self_platform_target": self_platform_target,
            }
        critical_scope = self._critical_continuation_scope(request, pool, paths)
        if critical_scope.get("status") == "blocked":
            return {
                "status": "blocked",
                "phase": "waiting_for_critical_decision",
                "reason": str(critical_scope.get("reason") or "critical_approval_scope_mismatch"),
                "paths": paths,
                "warnings": warnings,
                "workspace_evidence": workspace_evidence,
                "recovery_evidence": recovery_evidence,
                "effective_limits": effective_limits,
                "critical_scope": critical_scope,
            }
        effective_allowed_paths = self._effective_allowed_paths(request, envelope)
        if effective_allowed_paths.get("expanded"):
            return {
                "status": "blocked",
                "phase": "understanding_goal",
                "reason": "allowed_paths_expand_envelope",
                "paths": paths,
                "requested_allowed_paths": list(request.allowed_paths or []),
                "envelope_allowed_paths": list(((envelope.get("bounds") or {}).get("allowed_paths") or [])),
                "warnings": warnings,
                "workspace_evidence": workspace_evidence,
                "recovery_evidence": recovery_evidence,
                "effective_limits": effective_limits,
            }
        unsafe = [p for p in paths if not self._safe_relative_path(p)]
        if unsafe:
            return {
                "status": "blocked",
                "phase": "understanding_goal",
                "reason": "unsafe_path",
                "paths": unsafe,
                "warnings": warnings,
                "workspace_evidence": workspace_evidence,
                "recovery_evidence": recovery_evidence,
            }
        blocked_paths = self._unique_strings(list(((envelope.get("bounds") or {}).get("blocked_paths") or [])) + list(request.blocked_paths or []))
        blocked = [p for p in paths if self._matches_prefix(p, blocked_paths)]
        if blocked:
            return {
                "status": "blocked",
                "phase": "understanding_goal",
                "reason": "blocked_path",
                "paths": blocked,
                "warnings": warnings,
                "workspace_evidence": workspace_evidence,
                "recovery_evidence": recovery_evidence,
            }
        allowed = list(effective_allowed_paths.get("allowed_paths") or [])
        outside = [p for p in paths if allowed and not self._matches_prefix(p, allowed)]
        if outside:
            return {
                "status": "blocked",
                "phase": "understanding_goal",
                "reason": "path_outside_allowed_paths",
                "paths": outside,
                "warnings": warnings,
                "workspace_evidence": workspace_evidence,
                "recovery_evidence": recovery_evidence,
            }
        clarification_scope = self._clarification_scope(pool)
        clarification_allowed = list(clarification_scope.get("allowed_paths") or [])
        clarification_blocked = list(clarification_scope.get("blocked_paths") or [])
        clarification_blocked_paths = [
            p for p in paths
            if clarification_blocked and self._matches_prefix(p, clarification_blocked)
        ]
        if clarification_blocked_paths:
            return {
                "status": "blocked",
                "phase": "revising_plan_from_clarification",
                "reason": "path_blocked_by_clarification_scope",
                "paths": clarification_blocked_paths,
                "warnings": warnings,
                "workspace_evidence": workspace_evidence,
                "recovery_evidence": recovery_evidence,
                "effective_limits": effective_limits,
                "clarification_scope": clarification_scope,
            }
        clarification_outside = [
            p for p in paths
            if clarification_allowed and not self._matches_prefix(p, clarification_allowed)
        ]
        if clarification_outside:
            return {
                "status": "blocked",
                "phase": "revising_plan_from_clarification",
                "reason": "path_outside_clarification_allowed_paths",
                "paths": clarification_outside,
                "warnings": warnings,
                "workspace_evidence": workspace_evidence,
                "recovery_evidence": recovery_evidence,
                "effective_limits": effective_limits,
                "clarification_scope": clarification_scope,
            }
        return {
            "status": "ok",
            "normalized_profile": profile,
            "project_path": project_path,
            "effective_project_path": workspace_evidence.get("effective_project_path") or project_path,
            "paths": paths,
            "envelope_id": envelope_id,
            "effective_allowed_paths": allowed,
            "effective_blocked_paths": blocked_paths,
            "effective_limits": effective_limits,
            "critical_scope": critical_scope,
            "clarification_scope": clarification_scope,
            "self_platform_target": self_platform_target,
            "warnings": warnings,
            "workspace_evidence": workspace_evidence,
            "recovery_evidence": recovery_evidence,
        }

    @staticmethod
    def _classify_self_platform_target(paths: list[str]) -> dict[str, Any]:
        categories: dict[str, list[str]] = {
            "runtime": [],
            "policy_or_manifest": [],
            "tests": [],
            "docs": [],
        }
        for raw in paths:
            path = str(raw or "").replace("\\", "/").lstrip("./")
            if not path:
                continue
            if path.startswith(("agent/", "app/")) or path.startswith("web/js/atlas_") or path == "ui.html":
                categories["runtime"].append(path)
            elif path in {
                "docs/atlas_automation_phase_manifest.json",
                "docs/atlas_autonomous_execution_readiness_policy.md",
            }:
                categories["policy_or_manifest"].append(path)
            elif path.startswith("tests/test_atlas"):
                categories["tests"].append(path)
            elif path.startswith("docs/atlas_"):
                categories["docs"].append(path)
        matched = []
        for values in categories.values():
            matched.extend(values)
        is_self_platform = bool(matched)
        strict_review_required = bool(categories["runtime"] or categories["policy_or_manifest"])
        return {
            "is_self_platform": is_self_platform,
            "target_files": sorted(set(matched)),
            "categories": {key: sorted(set(value)) for key, value in categories.items() if value},
            "risk_level": "strict_gate" if strict_review_required else ("high" if is_self_platform else "low"),
            "strict_review_required": strict_review_required,
            "manual_review_required": bool(is_self_platform),
            "candidate_only": bool(is_self_platform),
            "candidate_workspace_required": bool(is_self_platform),
            "stable_runtime_mutation_enabled": False,
            "self_apply_enabled": False,
            "direct_merge_enabled": False,
            "remote_git_push_enabled": False,
            "release_pointer_switch_enabled": False,
        }

    def _self_platform_review_gate(self, metadata: dict[str, Any], pool: AtlasPlanPool) -> dict[str, Any]:
        preflight = metadata.get("preflight") if isinstance(metadata.get("preflight"), dict) else {}
        target = preflight.get("self_platform_target") if isinstance(preflight.get("self_platform_target"), dict) else {}
        if not target.get("is_self_platform"):
            return {}
        findings: list[dict[str, Any]] = []
        blocking: list[dict[str, Any]] = []

        def add(code: str, message: str, *, severity: str = "info", blocking_finding: bool = False, path: str = "") -> None:
            finding = {"code": code, "severity": severity, "message": message, "path": path, "blocking": blocking_finding}
            findings.append(finding)
            if blocking_finding:
                blocking.append(finding)

        add("manual_review_required", "Self-platform changes require manual review before draft PR readiness.", severity="warning")
        if target.get("strict_review_required"):
            add("strict_review_required", "Runtime or manifest/policy target requires strict review metadata.", severity="warning")
        for key in ("stable_runtime_mutation_enabled", "self_apply_enabled", "direct_merge_enabled", "remote_git_push_enabled", "release_pointer_switch_enabled"):
            if target.get(key) is not False:
                add(f"{key}_not_false", f"{key} must remain false for candidate-only self-platform work.", severity="error", blocking_finding=True)

        manifest_flags = self._manifest_self_platform_safety_flags()
        for key, value in manifest_flags.items():
            if value is not False:
                add(f"manifest_{key}_not_false", f"Manifest safety flag {key} must remain false.", severity="error", blocking_finding=True)

        for path, code in self._self_platform_forbidden_content_findings(pool):
            add(code, f"Forbidden self-platform enablement pattern detected in candidate content: {code}.", severity="error", blocking_finding=True, path=path)

        return {
            "status": "blocked" if blocking else "passed",
            "target_files": list(target.get("target_files") or []),
            "risk_level": target.get("risk_level", "high"),
            "findings": findings,
            "blocking_findings": blocking,
            "required_manual_review": True,
            "draft_pr_allowed": not blocking,
            "candidate_only": True,
            "stable_runtime_mutation_enabled": False,
            "self_apply_enabled": False,
            "direct_merge_enabled": False,
            "remote_git_push_enabled": False,
            "release_pointer_switch_enabled": False,
        }

    @staticmethod
    def _manifest_self_platform_safety_flags() -> dict[str, Any]:
        try:
            data = json.loads(Path("docs/atlas_automation_phase_manifest.json").read_text(encoding="utf-8"))
        except Exception:
            return {"manifest_read_failed": True}
        return {
            "stable_runtime_mutation_enabled": data.get("stable_runtime_mutation_enabled"),
            "self_apply_enabled": data.get("self_apply_enabled"),
            "direct_merge_enabled": data.get("direct_merge_enabled"),
            "remote_git_push_enabled": data.get("remote_git_push_enabled"),
            "vue_source_of_truth": data.get("vue_source_of_truth"),
            "default_conversational_shell_requires_vue": data.get("default_conversational_shell_requires_vue"),
            "default_conversational_shell_requires_vite": data.get("default_conversational_shell_requires_vite"),
        }

    @staticmethod
    def _self_platform_forbidden_content_findings(pool: AtlasPlanPool) -> list[tuple[str, str]]:
        patterns = {
            "raw_source_serving_enabled": ("raw_source_serving_enabled", "send_file(", "FileResponse("),
            "startup_npm_vite_vue_build_enabled": ("npm run vite", "vite --host", "startup_npm_vite_vue_build_enabled"),
            "arbitrary_unbounded_command_execution_enabled": ("arbitrary_unbounded_command_execution", "shell=True"),
            "vue_authority_enabled": ("vue_source_of_truth", "vue_authority_enabled"),
            "direct_merge_enabled": ("direct_merge_enabled",),
            "remote_git_push_enabled": ("remote_git_push_enabled",),
            "self_apply_enabled": ("self_apply_enabled",),
            "stable_runtime_mutation_enabled": ("stable_runtime_mutation_enabled",),
        }
        findings: list[tuple[str, str]] = []
        for item in getattr(pool, "items", []) or []:
            path = ",".join(getattr(item, "target_files", []) or [])
            metadata = getattr(item, "metadata", {}) or {}
            candidates = [str(metadata.get("proposed_content") or "")]
            for change in normalize_plan_item_file_changes(item):
                candidates.append(str(getattr(change, "content", "") or ""))
            content = "\n".join(candidates).lower()
            for code, tokens in patterns.items():
                if any(token.lower() in content for token in tokens) and ("true" in content or code in {"raw_source_serving_enabled", "startup_npm_vite_vue_build_enabled", "arbitrary_unbounded_command_execution_enabled"}):
                    findings.append((path, code))
        return findings

    @staticmethod
    def _self_platform_review_lines(metadata: dict) -> list[str]:
        gate = metadata.get("self_platform_review_gate") if isinstance(metadata.get("self_platform_review_gate"), dict) else {}
        if not gate:
            return ["not applicable"]
        lines = [
            f"status: {gate.get('status', 'unknown')}",
            f"required_manual_review: {bool(gate.get('required_manual_review'))}",
            f"draft_pr_allowed: {bool(gate.get('draft_pr_allowed'))}",
        ]
        for finding in gate.get("findings") or []:
            if isinstance(finding, dict):
                lines.append(f"{finding.get('severity', 'info')}: {finding.get('code', '')}")
        return lines

    @staticmethod
    def _critical_continuation_scope(
        request: AtlasAutonomousCodegenRequest,
        pool: AtlasPlanPool,
        paths: list[str],
    ) -> dict[str, Any]:
        metadata = pool.metadata if isinstance(pool.metadata, dict) else {}
        critical_event = metadata.get("critical_event") if isinstance(metadata.get("critical_event"), dict) else {}
        critical_decision = metadata.get("critical_decision") if isinstance(metadata.get("critical_decision"), dict) else {}
        if not critical_event or not critical_event.get("critical_event"):
            return {"status": "not_applicable"}
        if str(critical_decision.get("decision") or "").strip().lower() != "approved":
            return {
                "status": "blocked",
                "reason": "critical_event_waiting_for_user_decision",
                "critical_event": critical_event,
            }
        if critical_decision.get("bounded_continuation") is not True:
            return {
                "status": "blocked",
                "reason": "critical_approval_missing_bounded_scope",
                "critical_event": critical_event,
                "critical_decision": critical_decision,
            }
        approved_files = [
            str(path).replace("\\", "/")
            for path in (
                critical_decision.get("approved_files")
                or critical_decision.get("approved_scope")
                or critical_decision.get("approved_paths")
                or []
            )
            if str(path).strip()
        ]
        approved_item_ids = {
            str(item_id)
            for item_id in (critical_decision.get("approved_item_ids") or [])
            if str(item_id).strip()
        }
        target_item_ids = set(request.item_ids or [item.item_id for item in pool.items])
        unapproved_items = sorted(target_item_ids - approved_item_ids) if approved_item_ids else []
        unapproved_files = [
            path for path in paths
            if approved_files and not AtlasAutonomousCodegenOrchestratorService._matches_prefix(path, approved_files)
        ]
        if unapproved_items or unapproved_files or not approved_files:
            return {
                "status": "blocked",
                "reason": "critical_approval_scope_mismatch",
                "critical_event": critical_event,
                "critical_decision": critical_decision,
                "approved_files": approved_files,
                "approved_item_ids": sorted(approved_item_ids),
                "target_item_ids": sorted(target_item_ids),
                "unapproved_items": unapproved_items,
                "unapproved_files": unapproved_files,
            }
        return {
            "status": "approved_scope_valid",
            "critical_event": critical_event,
            "approved_files": approved_files,
            "approved_item_ids": sorted(approved_item_ids),
        }

    @staticmethod
    def _effective_limits(request: AtlasAutonomousCodegenRequest, envelope: dict) -> dict[str, Any]:
        bounds = envelope.get("bounds") if isinstance(envelope.get("bounds"), dict) else {}

        def positive_int(value: Any, fallback: int) -> int:
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                return fallback
            return parsed if parsed > 0 else fallback

        envelope_max_actions = positive_int(bounds.get("max_actions_per_loop"), int(request.max_actions))
        envelope_max_files = positive_int(bounds.get("max_files_changed"), int(request.max_changed_files_total))
        envelope_max_runtime = positive_int(bounds.get("max_runtime_seconds"), int(request.max_runtime_seconds))
        effective = {
            "max_actions": min(int(request.max_actions), envelope_max_actions),
            "max_items": min(int(request.max_items), envelope_max_actions),
            "max_runtime_seconds": min(int(request.max_runtime_seconds), envelope_max_runtime),
            "max_changed_files_total": min(int(request.max_changed_files_total), envelope_max_files),
            "max_changed_files_per_item": min(int(request.max_changed_files_per_item), envelope_max_files),
        }
        requested = {
            "max_actions": int(request.max_actions),
            "max_items": int(request.max_items),
            "max_runtime_seconds": int(request.max_runtime_seconds),
            "max_changed_files_total": int(request.max_changed_files_total),
            "max_changed_files_per_item": int(request.max_changed_files_per_item),
        }
        effective["clamped"] = any(effective[key] < requested[key] for key in requested)
        return effective

    @classmethod
    def _effective_allowed_paths(cls, request: AtlasAutonomousCodegenRequest, envelope: dict) -> dict[str, Any]:
        bounds = envelope.get("bounds") if isinstance(envelope.get("bounds"), dict) else {}
        envelope_allowed = [str(path).replace("\\", "/") for path in (bounds.get("allowed_paths") or []) if str(path)]
        requested_allowed = [str(path).replace("\\", "/") for path in (request.allowed_paths or []) if str(path)]
        if envelope_allowed and requested_allowed:
            expanded = [path for path in requested_allowed if not cls._matches_prefix(path, envelope_allowed)]
            return {"allowed_paths": requested_allowed, "expanded": bool(expanded), "expanded_paths": expanded}
        return {"allowed_paths": requested_allowed or envelope_allowed, "expanded": False, "expanded_paths": []}

    @staticmethod
    def _clarification_scope(pool: AtlasPlanPool) -> dict[str, Any]:
        metadata = pool.metadata if isinstance(pool.metadata, dict) else {}
        allowed = [
            str(path).replace("\\", "/")
            for path in (metadata.get("allowed_paths_after_clarification") or [])
            if str(path).strip()
        ]
        blocked = [
            str(path).replace("\\", "/")
            for path in (metadata.get("blocked_paths_after_clarification") or [])
            if str(path).strip()
        ]
        if not allowed and not blocked:
            return {"status": "not_applicable", "allowed_paths": [], "blocked_paths": []}
        return {"status": "active", "allowed_paths": allowed, "blocked_paths": blocked}

    @staticmethod
    def _unique_strings(values: list[str]) -> list[str]:
        out: list[str] = []
        for value in values:
            text = str(value or "").replace("\\", "/")
            if text and text not in out:
                out.append(text)
        return out

    def _workspace_evidence(
        self,
        request: AtlasAutonomousCodegenRequest,
        pool: AtlasPlanPool,
        project_path: str,
        profile: str,
    ) -> dict:
        metadata = request.metadata or {}
        envelope = request.envelope or {}
        work_target = str(metadata.get("work_target") or "").strip()
        if not work_target:
            if request.self_improvement:
                work_target = "platform_self_improvement"
            elif metadata.get("candidate_workspace_path") or metadata.get("candidate_workspace_plan_path"):
                work_target = "candidate_workspace"
            else:
                work_target = "ordinary_project"

        warnings: list[str] = []
        candidate_path = str(metadata.get("candidate_workspace_path") or "").strip()
        candidate_plan_path = str(metadata.get("candidate_workspace_plan_path") or "").strip()
        candidate_plan = self._load_candidate_workspace_plan(candidate_plan_path, warnings)
        if not candidate_path and candidate_plan:
            candidate_path = str(candidate_plan.get("candidate_root") or "")

        candidate_required = bool(
            request.self_improvement
            or work_target in {"platform_self_improvement", "candidate_workspace"}
            or envelope.get("candidate_workspace_required")
        )
        candidate_available = bool(candidate_path)
        level4_checkpoint_path = str(
            metadata.get("level4_checkpoint_path")
            or envelope.get("level4_checkpoint_path")
            or ""
        ).strip()
        recovery_manifest_ref = str(
            metadata.get("recovery_manifest_path")
            or (candidate_plan or {}).get("recovery_manifest_path")
            or ""
        ).strip()

        blocking_reason = ""
        if work_target == "stable_runtime":
            blocking_reason = "stable_runtime_mutation_forbidden"
        elif request.self_improvement:
            if profile != "autonomous_dev_agent":
                blocking_reason = "self_improvement_profile_required"
            elif not candidate_available:
                blocking_reason = "candidate_workspace_required"
            elif not level4_checkpoint_path:
                blocking_reason = "stable_checkpoint_evidence_required"
        elif work_target == "candidate_workspace" and not candidate_available:
            blocking_reason = "workspace_not_available"

        if candidate_required and not candidate_available and "candidate_workspace_missing" not in warnings:
            warnings.append("candidate_workspace_missing")
        if not recovery_manifest_ref and "recovery_manifest_missing" not in warnings:
            warnings.append("recovery_manifest_missing")

        effective_project_path = candidate_path if candidate_available else project_path
        status = "blocked" if blocking_reason else ("ready" if effective_project_path else "missing")
        candidate_workspace_id = str(
            metadata.get("candidate_workspace_id")
            or (candidate_plan or {}).get("candidate_workspace_id")
            or (candidate_plan or {}).get("workspace_id")
            or (Path(candidate_plan_path).stem if candidate_plan_path else "")
        ).strip()
        return {
            "status": status,
            "work_target": work_target,
            "project_path": project_path,
            "effective_project_path": effective_project_path,
            "candidate_workspace_id": candidate_workspace_id,
            "candidate_workspace_root": candidate_path,
            "candidate_workspace_required": candidate_required,
            "candidate_workspace_available": candidate_available,
            "candidate_workspace_path": candidate_path,
            "candidate_workspace_plan_path": candidate_plan_path,
            "candidate_workspace_plan_status": str((candidate_plan or {}).get("status") or ""),
            "level4_checkpoint_required": bool(request.self_improvement),
            "level4_checkpoint_path": level4_checkpoint_path,
            "recovery_manifest_path": recovery_manifest_ref,
            "stable_runtime_mutation_enabled": False,
            "stable_runtime_mutation_performed": False,
            "self_apply_enabled": False,
            "self_apply_performed": False,
            "direct_merge_enabled": False,
            "remote_git_push_enabled": False,
            "recovery_execution_performed": False,
            "blocking_reason": blocking_reason,
            "warnings": warnings,
        }

    @staticmethod
    def _load_candidate_workspace_plan(path: str, warnings: list[str]) -> dict:
        if not path:
            return {}
        try:
            return load_candidate_workspace_plan(manifest_path=path)
        except (FileNotFoundError, ValueError, json.JSONDecodeError, OSError) as exc:
            warnings.append(f"candidate_workspace_plan_unavailable:{type(exc).__name__}")
            return {}

    def _recovery_evidence(self, request: AtlasAutonomousCodegenRequest, pool: AtlasPlanPool) -> dict:
        metadata = request.metadata or {}
        refs = {
            "recovery_manifest_path": str(metadata.get("recovery_manifest_path") or ""),
            "restore_plan_ref": str(metadata.get("restore_plan_ref") or ""),
            "rollback_plan_ref": str(metadata.get("rollback_plan_ref") or ""),
        }
        warnings: list[str] = []
        if not any(refs.values()):
            warnings.append("recovery_reference_missing")
        try:
            summary = AtlasRecoveryService(self.journal).recover_pool(pool.pool_id).model_dump()
        except Exception as exc:  # recovery metadata must not block or fabricate execution
            summary = {"status": "unavailable", "errors": [f"recovery_summary_unavailable:{type(exc).__name__}"]}
        if summary.get("status") in {"no_workspace", "no_plan_pool", "no_pipeline_run", "unavailable"}:
            warnings.append(f"recovery_summary_{summary.get('status')}")
        snapshot_manifest_path = refs["recovery_manifest_path"]
        restore_available = bool(snapshot_manifest_path or refs["restore_plan_ref"] or refs["rollback_plan_ref"])
        return {
            "status": str(summary.get("status") or "unknown"),
            "references": refs,
            "snapshot_manifest_path": snapshot_manifest_path,
            "changed_files": [],
            "restore_available": restore_available,
            "summary": summary,
            "restore_executed": False,
            "rollback_executed": False,
            "recovery_execution_performed": False,
            "warnings": sorted(set(warnings)),
        }

    def _prepare_draft_pr_artifact(
        self,
        *,
        result: AtlasAutonomousCodegenResult,
        request: AtlasAutonomousCodegenRequest,
        pool: AtlasPlanPool,
        autopilot,
    ) -> dict[str, Any]:
        changed_files = self._changed_files_from_autopilot(autopilot)
        readiness = self._draft_pr_readiness(result=result, changed_files=changed_files, autopilot=autopilot)
        success = bool(readiness.get("ready"))
        metadata = request.metadata or {}
        title = str(metadata.get("draft_pr_title") or f"Atlas autonomous update: {pool.root_goal[:80]}").strip()
        base_ref = str(metadata.get("base_ref") or "main").strip() or "main"
        head_branch = str(metadata.get("head_branch") or "codex/atlas-autonomous-update").strip()
        body = self._build_draft_pr_body(
            result=result,
            pool=pool,
            changed_files=changed_files,
            autopilot=autopilot,
        )
        artifact_id = f"draftpr_artifact_{uuid4().hex[:10]}"
        root = self.data_root / "atlas" / "autonomous_codegen" / result.pool_id / result.orchestrator_run_id
        artifact_path = root / "draft_pr_artifact.json"
        body_path = root / "draft_pr_body.md"
        envelope = request.envelope or {}
        creation_requested = bool(metadata.get("allow_draft_pr_creation") or envelope.get("allow_draft_pr_creation"))
        creation_allowed = bool(envelope.get("allow_draft_pr_creation"))
        creation_result: dict[str, Any] = {
            "attempted": False,
            "requested": creation_requested,
            "allowed": creation_allowed,
            "status": "not_requested" if not creation_requested else "blocked",
            "blocked_reasons": (
                []
                if not creation_requested
                else ["draft_pr_envelope_permission_required"] if not creation_allowed
                else ["draft_pr_client_required"]
            ),
            "draft_pr_created": False,
            "draft_pr_updated": False,
            "direct_merge_performed": False,
            "remote_git_push_performed": False,
        }
        if success and creation_allowed and self.draft_pr_client is not None:
            creation_result = self._create_draft_pr_with_injected_client(
                base_ref=base_ref,
                head_branch=head_branch,
                title=title,
                body=body,
            )
        elif not success:
            creation_result = {
                **creation_result,
                "status": "not_ready",
                "blocked_reasons": list(readiness.get("blocked_reasons") or ["autonomous_run_not_ready"]),
            }

        artifact = {
            "schema_version": "atlas.autonomous_codegen_draft_pr_artifact.v1",
            "artifact_id": artifact_id,
            "status": "ready" if success else "not_ready",
            "ready": success,
            "readiness": readiness,
            "pool_id": result.pool_id,
            "run_id": result.run_id,
            "orchestrator_run_id": result.orchestrator_run_id,
            "autopilot_run_id": str((result.metadata or {}).get("autopilot_run_id") or ""),
            "title": title,
            "base_ref": base_ref,
            "head_branch": head_branch,
            "changed_files": changed_files,
            "body": body,
            "body_path": str(body_path),
            "artifact_path": str(artifact_path),
            "branch_instructions": [
                f"Review local branch {head_branch}.",
                f"Open a draft PR from {head_branch} into {base_ref} with the generated body.",
            ],
            "safety": {
                "injected_client_only": True,
                "draft_pr_envelope_required": True,
                "draft_pr_creation_allowed": creation_allowed,
                "direct_merge_enabled": False,
                "direct_merge_performed": False,
                "remote_git_push_enabled": False,
                "remote_git_push_performed": False,
                "runtime_auto_merge_enabled": False,
                "self_apply_enabled": False,
                "stable_runtime_mutation_enabled": False,
            },
            "creation_result": creation_result,
        }
        root.mkdir(parents=True, exist_ok=True)
        body_path.write_text(body, encoding="utf-8")
        artifact_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            key: artifact[key]
            for key in (
                "schema_version",
                "artifact_id",
                "status",
                "ready",
                "artifact_path",
                "body_path",
                "changed_files",
                "readiness",
                "safety",
                "creation_result",
            )
        }

    def _create_draft_pr_with_injected_client(
        self,
        *,
        base_ref: str,
        head_branch: str,
        title: str,
        body: str,
    ) -> dict[str, Any]:
        assert self.draft_pr_client is not None
        base = {
            "attempted": True,
            "allowed": True,
            "draft_pr_created": False,
            "draft_pr_updated": False,
            "direct_merge_performed": False,
            "remote_git_push_performed": False,
        }
        try:
            response = self.draft_pr_client.create_draft_pull_request(
                base_ref=base_ref,
                head_branch=head_branch,
                title=title,
                body=body,
            )
        except Exception as exc:
            return {**base, "status": "blocked", "blocked_reasons": [f"draft_pr_client_error:{type(exc).__name__}"]}
        blocked: list[str] = []
        if not response.get("number"):
            blocked.append("draft_pr_number_required")
        if not (response.get("html_url") or response.get("url")):
            blocked.append("draft_pr_url_required")
        if response.get("draft") is not True:
            blocked.append("draft_pr_must_be_draft")
        if blocked:
            return {**base, "status": "blocked", "blocked_reasons": blocked}
        return {
            **base,
            "status": "created",
            "blocked_reasons": [],
            "draft_pr_created": True,
            "draft_pr_number": response.get("number"),
            "draft_pr_url": response.get("html_url") or response.get("url"),
            "draft_pr_api_url": response.get("url") or "",
            "draft": True,
        }

    def _build_draft_pr_body(self, *, result: AtlasAutonomousCodegenResult, pool: AtlasPlanPool, changed_files: list[str], autopilot) -> str:
        metadata = pool.metadata or {}
        return "\n".join(
            [
                "## Summary",
                f"- Autonomous Atlas run status: {result.status}.",
                f"- Goal: {pool.root_goal}",
                "",
                "## Scope",
                f"- Pool: {pool.pool_id}",
                f"- Processed items: {getattr(autopilot, 'processed_count', 0)}",
                f"- Completed items: {getattr(autopilot, 'completed_count', 0)}",
                f"- Failed items: {getattr(autopilot, 'failed_count', 0)}",
                "",
                "## Safety constraints",
                "- backend workflow_state authoritative",
                "- UI supervision/display only",
                "- no direct merge",
                "- no remote git push",
                "- no self-apply",
                "- no stable runtime mutation",
                "- no Vue authority",
                "",
                "## Self-platform review gate",
                self._markdown_list(self._self_platform_review_lines(result.metadata if isinstance(result.metadata, dict) else {})),
                "",
                "## Supervised auto-merge readiness",
                self._markdown_list(self._auto_merge_readiness_lines(result.metadata if isinstance(result.metadata, dict) else {})),
                "",
                "## Changed files",
                self._markdown_list(changed_files),
                "",
                "## Tests / verification",
                self._markdown_list(self._verification_evidence(autopilot)),
                "",
                "## Clarification decisions",
                self._markdown_list(self._metadata_lines(metadata, "clarification_answers", "clarifications")),
                "",
                "## Critical events / user decisions",
                self._markdown_list(self._metadata_lines(metadata, "critical_decisions", "critical_events", "user_decisions")),
                "",
                "## Repair attempts",
                self._markdown_list(self._repair_attempts(autopilot)),
                "",
                "## Recovery info",
                self._markdown_list(self._recovery_lines(result.metadata if isinstance(result.metadata, dict) else {})),
                "",
                "## Remaining risks",
                self._markdown_list(list(result.warnings or []) + list(result.errors or [])),
                "",
                "## Rollback notes",
                self._markdown_list(self._rollback_notes(pool)),
                "",
                "## Remaining manual review steps",
                self._markdown_list(self._manual_review_steps(result.metadata if isinstance(result.metadata, dict) else {})),
            ]
        )

    def _draft_pr_readiness(self, *, result: AtlasAutonomousCodegenResult, changed_files: list[str], autopilot) -> dict[str, Any]:
        blocked_reasons: list[str] = []
        if result.status not in {"completed", "partial"}:
            blocked_reasons.append("autonomous_run_not_successful")
        if not changed_files:
            blocked_reasons.append("changed_files_required")
        if not self._verification_evidence(autopilot):
            blocked_reasons.append("verification_evidence_required")
        metadata = result.metadata if isinstance(result.metadata, dict) else {}
        repair_plan = metadata.get("repair_plan") if isinstance(metadata.get("repair_plan"), dict) else {}
        post_repair = metadata.get("post_repair_verification_result") if isinstance(metadata.get("post_repair_verification_result"), dict) else {}
        if repair_plan.get("post_repair_verification_required") and str(post_repair.get("status") or "") != "passed":
            blocked_reasons.append("post_repair_verification_required")
        if metadata.get("verification_failure_summary"):
            blocked_reasons.append("verification_failure_unresolved")
        ci_plan = metadata.get("ci_repair_plan") if isinstance(metadata.get("ci_repair_plan"), dict) else {}
        ci_post_repair = metadata.get("post_ci_repair_verification_result") if isinstance(metadata.get("post_ci_repair_verification_result"), dict) else {}
        if metadata.get("post_ci_repair_verification_required") and str(ci_post_repair.get("status") or "") != "passed":
            blocked_reasons.append("post_ci_repair_verification_required")
        if ci_plan.get("status") == "planned":
            blocked_reasons.append("ci_failure_repair_unverified")
        self_platform_gate = metadata.get("self_platform_review_gate") if isinstance(metadata.get("self_platform_review_gate"), dict) else {}
        if self_platform_gate and not self_platform_gate.get("draft_pr_allowed"):
            blocked_reasons.append("self_platform_review_gate_blocked")
        if result.stop_reason in {"clarification_required", "critical_event_waiting_for_user_decision"}:
            blocked_reasons.append(result.stop_reason)
        return {
            "ready": not blocked_reasons,
            "blocked_reasons": blocked_reasons,
            "changed_files_present": bool(changed_files),
            "verification_evidence_present": bool(self._verification_evidence(autopilot)),
        }

    def _auto_merge_readiness(self, metadata: dict[str, Any], autopilot, request: AtlasAutonomousCodegenRequest) -> dict[str, Any]:
        request_metadata = request.metadata or {}
        draft = metadata.get("draft_pr_readiness") if isinstance(metadata.get("draft_pr_readiness"), dict) else {}
        preflight = metadata.get("preflight") if isinstance(metadata.get("preflight"), dict) else {}
        self_platform_target = preflight.get("self_platform_target") if isinstance(preflight.get("self_platform_target"), dict) else {}
        self_platform_gate = metadata.get("self_platform_review_gate") if isinstance(metadata.get("self_platform_review_gate"), dict) else {}
        safety_grep = request_metadata.get("safety_grep_result") if isinstance(request_metadata.get("safety_grep_result"), dict) else {}
        drift = request_metadata.get("manifest_policy_drift_result") if isinstance(request_metadata.get("manifest_policy_drift_result"), dict) else {}
        ci_status = str(request_metadata.get("ci_status") or request_metadata.get("ci_state") or "").lower()
        user_approval_state = str(request_metadata.get("user_approval_state") or "").lower()
        blocking_reasons: list[str] = []
        required_manual_approvals: list[str] = []

        if not metadata.get("changed_files"):
            blocking_reasons.append("changed_files_required")
        if not self._verification_evidence(autopilot):
            blocking_reasons.append("verification_evidence_required")
        if not draft.get("ready"):
            blocking_reasons.append("draft_pr_readiness_required")
        if ci_status not in {"green", "passed", "success"}:
            blocking_reasons.append("ci_green_required_missing")
        if str(safety_grep.get("status") or "").lower() != "passed":
            blocking_reasons.append("safety_grep_pass_required")
        if str(drift.get("status") or "").lower() not in {"passed", "clean"}:
            blocking_reasons.append("manifest_policy_drift_check_required")
        if self_platform_target.get("is_self_platform") and not self_platform_gate:
            blocking_reasons.append("self_platform_review_gate_required")
        if self_platform_gate and not self_platform_gate.get("draft_pr_allowed"):
            blocking_reasons.append("self_platform_review_gate_blocked")
        if user_approval_state != "approved":
            blocking_reasons.append("user_approval_required")
            required_manual_approvals.append("explicit_supervised_merge_readiness_approval")

        ready = not blocking_reasons
        return {
            "status": "ready" if ready else "blocked",
            "ready": ready,
            "blocking_reasons": sorted(set(blocking_reasons)),
            "required_manual_approvals": required_manual_approvals,
            "ci_green_required": True,
            "ci_status": ci_status or "missing",
            "safety_grep_status": str(safety_grep.get("status") or "missing"),
            "manifest_policy_drift_status": str(drift.get("status") or "missing"),
            "self_platform_gate_status": str(self_platform_gate.get("status") or ("missing" if self_platform_target.get("is_self_platform") else "not_applicable")),
            "future_merge_gate_required": True,
            "manual_action_required_for_merge": True,
            "direct_merge_enabled": False,
            "remote_git_push_enabled": False,
            "merge_executed": False,
            "merged": False,
        }

    @staticmethod
    def _verification_evidence(autopilot) -> list[str]:
        lines: list[str] = []
        for item in getattr(autopilot, "item_results", []) or []:
            verification = getattr(item, "verification_result", None) or {}
            if isinstance(verification, dict) and verification:
                lines.append(f"{getattr(item, 'item_id', '')}: {verification.get('status', 'unknown')}")
        return lines

    @staticmethod
    def _recovery_lines(metadata: dict) -> list[str]:
        evidence = metadata.get("recovery_evidence") if isinstance(metadata.get("recovery_evidence"), dict) else {}
        if not evidence:
            return ["No recovery evidence recorded."]
        return [
            f"status: {evidence.get('status') or 'unknown'}",
            f"snapshot_manifest_path: {evidence.get('snapshot_manifest_path') or '(none)'}",
            f"changed_files: {', '.join(evidence.get('changed_files') or []) or '(none)'}",
            f"restore_available: {bool(evidence.get('restore_available'))}",
            f"restore_executed: {bool(evidence.get('restore_executed'))}",
            f"rollback_executed: {bool(evidence.get('rollback_executed'))}",
            f"recovery_execution_performed: {bool(evidence.get('recovery_execution_performed'))}",
        ]

    @staticmethod
    def _manual_review_steps(metadata: dict) -> list[str]:
        readiness = metadata.get("draft_pr_readiness") if isinstance(metadata.get("draft_pr_readiness"), dict) else {}
        steps = [
            "Review changed files and verification evidence.",
            "Confirm safety constraints remain false before opening or updating any PR.",
        ]
        blocked = list(readiness.get("blocked_reasons") or [])
        if blocked:
            steps.append("Resolve readiness blockers: " + ", ".join(str(b) for b in blocked))
        return steps

    @staticmethod
    def _auto_merge_readiness_lines(metadata: dict) -> list[str]:
        readiness = metadata.get("auto_merge_readiness") if isinstance(metadata.get("auto_merge_readiness"), dict) else {}
        if not readiness:
            return ["not evaluated"]
        lines = [
            f"status: {readiness.get('status', 'unknown')}",
            f"ready: {bool(readiness.get('ready'))}",
            f"ci_green_required: {bool(readiness.get('ci_green_required'))}",
            "direct_merge_enabled: false",
            "merge_executed: false",
            "merge requires explicit future gate/manual action",
        ]
        blockers = list(readiness.get("blocking_reasons") or [])
        if blockers:
            lines.append("blocking_reasons: " + ", ".join(str(item) for item in blockers))
        approvals = list(readiness.get("required_manual_approvals") or [])
        if approvals:
            lines.append("required_manual_approvals: " + ", ".join(str(item) for item in approvals))
        return lines

    @staticmethod
    def _repair_attempts(autopilot) -> list[str]:
        lines: list[str] = []
        for item in getattr(autopilot, "item_results", []) or []:
            metadata = getattr(item, "metadata", {}) or {}
            for key in ("bounded_retry_result", "self_correction_result"):
                if metadata.get(key):
                    lines.append(f"{getattr(item, 'item_id', '')}: {key}")
        return lines

    @staticmethod
    def _metadata_lines(metadata: dict, *keys: str) -> list[str]:
        lines: list[str] = []
        for key in keys:
            value = metadata.get(key)
            if not value:
                continue
            if isinstance(value, list):
                lines.extend(json.dumps(item, ensure_ascii=False, sort_keys=True) for item in value)
            else:
                lines.append(json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, dict) else str(value))
        return lines

    @staticmethod
    def _rollback_notes(pool: AtlasPlanPool) -> list[str]:
        lines: list[str] = []
        for item in pool.items:
            for note in getattr(item, "rollback_plan", []) or []:
                lines.append(f"{item.item_id}: {note}")
        return lines

    @staticmethod
    def _markdown_list(values: list[str]) -> str:
        cleaned = [str(value) for value in values if str(value).strip()]
        if not cleaned:
            return "- None recorded."
        return "\n".join(f"- {value}" for value in cleaned)

    @staticmethod
    def _requested_paths(request: AtlasAutonomousCodegenRequest, pool: AtlasPlanPool) -> list[str]:
        ids = set(request.item_ids or [item.item_id for item in pool.items])
        paths: list[str] = []
        for item in pool.items:
            if item.item_id not in ids:
                continue
            for path in item.target_files or []:
                text = str(path).replace("\\", "/")
                if text not in paths:
                    paths.append(text)
        return paths

    @staticmethod
    def _safe_relative_path(path: str) -> bool:
        pure = PurePosixPath(str(path or ""))
        return bool(path) and not pure.is_absolute() and ".." not in pure.parts

    @staticmethod
    def _matches_prefix(path: str, prefixes: list[str]) -> bool:
        normalized = str(path or "").replace("\\", "/").strip("/")
        for prefix in prefixes or []:
            pfx = str(prefix or "").replace("\\", "/").strip("/")
            if not pfx:
                continue
            if normalized == pfx or normalized.startswith(pfx + "/"):
                return True
        return False

    @staticmethod
    def _changed_files_from_autopilot(autopilot) -> list[str]:
        changed: list[str] = []
        for item in getattr(autopilot, "item_results", []) or []:
            for path in getattr(item, "changed_files", []) or []:
                if path not in changed:
                    changed.append(path)
        return changed

    def _build_repairable_verification_evidence(self, request: AtlasAutonomousCodegenRequest, autopilot) -> dict[str, Any]:
        failures = []
        for item in getattr(autopilot, "item_results", []) or []:
            summary = self._repairable_failure_summary(item, max_retries=int(request.max_retries or 0))
            if summary:
                failures.append(summary)
        if not failures:
            return {}
        changed_files = self._changed_files_from_autopilot(autopilot)
        affected_files = []
        for summary in failures:
            for path in summary.get("affected_files") or []:
                if path not in affected_files:
                    affected_files.append(path)
        allowed_repair_files = self._allowed_repair_files(
            affected_files=affected_files,
            changed_files=changed_files,
            allowed_paths=request.allowed_paths or list((((request.envelope or {}).get("bounds") or {}).get("allowed_paths") or [])),
            blocked_paths=request.blocked_paths or list((((request.envelope or {}).get("bounds") or {}).get("blocked_paths") or [])),
        )
        repair_plan = {
            "status": "planned" if allowed_repair_files else "blocked",
            "failure_summary": failures[0],
            "affected_files": affected_files,
            "allowed_repair_files": allowed_repair_files,
            "concrete_repair_steps": failures[0].get("recommended_repair_steps") or [],
            "retry_index": 0,
            "max_retries": int(request.max_retries or 0),
            "post_repair_verification_required": True,
            "blocked_reasons": [] if allowed_repair_files else ["no_allowed_repair_files"],
        }
        return {
            "verification_failure_summary": failures[0],
            "verification_failure_summaries": failures,
            "repair_plan": repair_plan,
            "repair_attempts": [
                {
                    "status": "planned_not_executed",
                    "reason": "bounded_repair_patch_generation_not_started",
                    "retry_index": 0,
                    "post_repair_verification_required": True,
                }
            ],
            "files_allowed_for_repair": allowed_repair_files,
            "retry_count": 0,
            "post_repair_verification_result": {"status": "not_run", "reason": "repair_not_applied"},
            "final_status": "verification_failed_repair_planned" if allowed_repair_files else "verification_failed_repair_blocked",
        }

    @staticmethod
    def _repairable_failure_summary(item, *, max_retries: int) -> dict[str, Any]:
        verification = getattr(item, "verification_result", None) or {}
        warnings = []
        warnings.extend(str(w) for w in (verification.get("warnings") or []) if str(w))
        warnings.extend(str(w) for w in (getattr(item, "warnings", []) or []) if str(w))
        reason = str(getattr(item, "reason", "") or "")
        if reason.startswith("verification_failed:"):
            warnings.append(reason.replace("verification_failed:", "", 1))
        visual_contract_failed = "visual_contract_failed" in warnings
        visual_missing = [w for w in warnings if w.startswith("visual_missing:")]
        browser_smoke_failed = [w for w in warnings if w.startswith("browser_smoke_failed:")]
        repairable_visual_missing = [
            w for w in visual_missing
            if w in {"visual_missing:animation_signal", "visual_missing:motion_signal", "visual_missing:color_mutation_signal"}
        ]
        browser_repairable = [
            w for w in browser_smoke_failed
            if "playwright_error" in w or visual_contract_failed or visual_missing
        ]
        if not (visual_contract_failed or repairable_visual_missing or browser_repairable):
            return {}
        affected_files = list(getattr(item, "changed_files", []) or [])
        failed_contracts = list(dict.fromkeys(
            (["visual_contract_failed"] if visual_contract_failed else [])
            + repairable_visual_missing
            + browser_repairable
        ))
        verification_tool_error = next((w for w in browser_smoke_failed if "playwright_error" in w), "")
        return {
            "item_id": str(getattr(item, "item_id", "") or ""),
            "user_facing_title": "Visual verification failed: game does not show required motion/animation evidence",
            "user_facing_summary": (
                f"Atlas changed {', '.join(affected_files) or 'the generated files'}, but verification could not detect "
                "visible animation, motion, or color/state changes. Browser smoke may also have failed, so Atlas should "
                "inspect the generated HTML/CSS/JS and repair the runtime loop or visible signals."
            ),
            "failed_contracts": failed_contracts,
            "likely_cause": "Missing or non-observable requestAnimationFrame loop, visible motion, canvas/DOM state mutation, or browser runtime signal.",
            "recommended_repair_steps": [
                "inspect index.html and related style/script files",
                "add or fix requestAnimationFrame loop",
                "ensure visible object position changes over time",
                "ensure canvas/DOM visual state changes are observable",
                "add visible color/state mutation where appropriate",
                "preserve existing game requirements",
                "rerun focused visual verification",
            ],
            "affected_files": affected_files,
            "repair_scope": "changed_files_only",
            "can_attempt_bounded_repair": max_retries > 0,
            "retry_count_remaining": max(0, max_retries),
            "verification_tool_error": verification_tool_error,
            "app_visual_contract_failed": visual_contract_failed,
        }

    def _allowed_repair_files(
        self,
        *,
        affected_files: list[str],
        changed_files: list[str],
        allowed_paths: list[str],
        blocked_paths: list[str],
    ) -> list[str]:
        changed = set(changed_files or [])
        candidates = [path for path in affected_files if path in changed]
        if not candidates:
            candidates = list(changed_files or [])
        allowed: list[str] = []
        for path in candidates:
            if not self._safe_relative_path(path):
                continue
            if self._matches_prefix(path, blocked_paths or []):
                continue
            if allowed_paths and not self._matches_prefix(path, allowed_paths):
                continue
            if path not in allowed:
                allowed.append(path)
        return allowed

    def _item_has_patch_content(self, item) -> bool:
        md = item.metadata or {}
        patch_proposal = md.get("patch_proposal") or {}
        file_changes = md.get("file_changes") if isinstance(md.get("file_changes"), list) else []
        file_change_content = bool(file_changes) and all(isinstance(fc, dict) and has_file_change_content(fc) for fc in file_changes)
        return bool(
            file_change_content
            or (md.get("patch") or "")
            or (md.get("content") or "")
            or (md.get("proposed_content") or "")
            or (md.get("unified_diff_preview") or "")
            or (patch_proposal.get("proposed_content") or "")
            or (patch_proposal.get("unified_diff_preview") or "")
            or ((md.get("safe_apply") or {}).get("patch") or "")
        )

    def _is_hard_blocked_item(self, item) -> bool:
        if str(getattr(item, "risk_level", "")).lower() == "critical":
            return True
        action_type = normalize_safe_apply_action_type((item.metadata or {}).get("action_type"))
        return action_type in _HARD_BLOCK_ACTION_TYPES

    def _emit(self, event_type: str, pool_id: str, run_id: str, orchestrator_run_id: str, **kw) -> None:
        if not run_id:
            return
        self.journal.append_event(
            pool_id,
            run_id,
            {
                "event_type": event_type,
                "pool_id": pool_id,
                "run_id": run_id,
                "orchestrator_run_id": orchestrator_run_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                **kw,
            },
        )

    def save_result(self, result: AtlasAutonomousCodegenResult) -> None:
        root = self.data_root / "atlas" / "autonomous_codegen" / result.pool_id
        root.mkdir(parents=True, exist_ok=True)
        payload = result.model_dump()
        (root / f"{result.orchestrator_run_id}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        (root / "latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
