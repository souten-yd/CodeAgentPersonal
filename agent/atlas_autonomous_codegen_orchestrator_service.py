from __future__ import annotations

import hashlib
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
from agent.atlas_multi_item_autopilot_schema import (
    AtlasAutopilotItemResult,
    AtlasMultiItemAutopilotRequest,
    AtlasMultiItemAutopilotResult,
)
from agent.atlas_patch_generation_state import is_patch_generation_success
from agent.atlas_patch_proposal_schema import AtlasPatchProposalRequest
from agent.atlas_plan_item_file_changes import has_file_change_content, normalize_plan_item_file_changes
from agent.atlas_recovery_service import AtlasRecoveryService
from agent.atlas_automation_profile_resolver import is_full_auto_context
from agent.twin_control_plane.active_integration import PipelineMode
from agent.twin_control_plane.pipeline_integration import (
    build_twin_pipeline_evidence,
    ensure_project_twin,
    expand_changed_refs_to_symbols,
    evaluate_twin_post_apply,
    load_project_twin_store,
    refresh_project_twin,
    resolve_block_schema,
    resolve_block_unverified,
    resolve_build_project_twin,
    python_schema_snapshot,
    resolve_gate_blocking,
    resolve_pipeline_mode,
    resolve_twin_autobuild,
    try_project_twin_impact,
    twin_gate_block_reason,
)

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
    """Compose plan -> per-item generate/review/apply/verify into one autonomous call.

    This adds NO new gate logic: item apply delegates to AtlasMultiItemAutopilotService, which already
    inherits the workstream-1 full_auto relaxation. The safety boundary is the plan-time critique
    gate (Phase 1 stop) plus the pre-apply snapshot/rollback inside the multi-item engine.
    """

    def __init__(self, *, storage, journal, patch_proposal_service, multi_item_autopilot_service, data_root=None, draft_pr_client: DraftPullRequestClient | None = None, project_twin_store=None):
        self.storage = storage
        self.journal = journal
        # Optional Project Twin store for real impact evidence. Absent by default (there is
        # no persistent per-project Twin store), so impact is recorded as unavailable.
        self.project_twin_store = project_twin_store
        # Accumulates LLM token usage (prompt / completion / total + thinking / output) across
        # all model calls in a run, fed by the adapter's on_usage callback (wired by the API).
        self.llm_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
                          "thinking_tokens": 0, "output_tokens": 0, "calls": 0}
        self.patch_proposal_service = patch_proposal_service
        self.multi_item_autopilot_service = multi_item_autopilot_service
        self.data_root = Path(data_root or getattr(journal, "root_dir", "ca_data"))
        self.draft_pr_client = draft_pr_client

    def accumulate_llm_usage(self, usage: dict) -> None:
        """Add one model call's token usage into the run total (called by the adapter)."""
        try:
            for k in ("prompt_tokens", "completion_tokens", "total_tokens", "thinking_tokens", "output_tokens"):
                self.llm_usage[k] = int(self.llm_usage.get(k, 0)) + int((usage or {}).get(k) or 0)
            self.llm_usage["calls"] = int(self.llm_usage.get("calls", 0)) + 1
        except Exception:  # pragma: no cover - defensive
            return

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
        # Attach a Forge-evaluated model identity (when unset) so capability-profile-driven
        # adaptation — route selection, decomposition tier, learned evidence — is active for the
        # whole run instead of neutral. Identity only; execution routing is unchanged.
        request = self._ensure_forge_model_identity(request)
        preflight = self._preflight(request, pool)
        out.metadata["preflight"] = preflight
        out.metadata["workspace_evidence"] = preflight.get("workspace_evidence", {})
        out.metadata["recovery_evidence"] = preflight.get("recovery_evidence", {})
        ci_failure_metadata = self._ci_failure_metadata(request, pool)
        if ci_failure_metadata:
            out.metadata.update(ci_failure_metadata)
        # Twin Control Plane evidence seam. Advisory for execution authority; when the
        # blocking gate is enabled it may stop the run on a genuine policy prerequisite.
        # Guarded so it can never break the legacy flow.
        twin_block_reason = self._attach_twin_control_plane(out, request, pool)
        if twin_block_reason:
            out.phase = "adversarial_review"
            out.status = "blocked_safety_review"
            out.stop_reason = twin_block_reason
            self._emit("autonomous_codegen_blocked_twin_gate", request.pool_id, run_id, orchestrator_run_id, status=out.status, reason=out.stop_reason)
            self.save_result(out)
            return out
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
        pool_status = str(getattr(pool, "status", "")).lower()
        revision_required = bool((pool.metadata or {}).get("plan_revision_required"))
        approval_required = pool_status == "approval_required"
        # A post-clarification safety block stays blocked unless a human granted an explicit override
        # (which also flips the pool back to "ready"). Without the override, surface a clean
        # blocked_safety_review with the recorded reason — never silently dispatch a 0/N apply.
        override_granted = bool((pool.metadata or {}).get("safety_override_granted_after_clarification"))
        safety_blocked = pool_status == "blocked_safety_review" and not override_granted
        if revision_required or approval_required or safety_blocked or pool_status in {"needs_scope_confirmation", "waiting_for_critical_decision"}:
            out.status = "blocked_safety_review"
            if pool_status == "needs_scope_confirmation":
                out.phase = "needs_scope_confirmation"
                out.stop_reason = "clarification_required"
            elif pool_status == "waiting_for_critical_decision":
                out.phase = "waiting_for_critical_decision"
                out.stop_reason = "critical_event_waiting_for_user_decision"
            elif safety_blocked:
                out.phase = "revising_plan_from_clarification"
                out.stop_reason = str(
                    (pool.metadata or {}).get("safety_gate_block_reason_after_clarification")
                    or "safety_gate_blocked_after_clarification"
                )
            else:
                out.stop_reason = "plan_revision_required" if revision_required else "approval_required"
            self._emit("autonomous_codegen_blocked_safety_review", request.pool_id, run_id, orchestrator_run_id, status=out.status, reason=out.stop_reason)
            self.save_result(out)
            return out

        # ── Phase 2/3: interleaved item loop ──────────────────────────────────────────────────
        effective_limits = preflight.get("effective_limits") if isinstance(preflight.get("effective_limits"), dict) else {}
        effective_max_actions = int(effective_limits.get("max_actions") or request.max_actions)
        effective_max_items = int(effective_limits.get("max_items") or request.max_items)
        effective_max_runtime_seconds = int(effective_limits.get("max_runtime_seconds") or request.max_runtime_seconds)
        effective_max_changed_files_total = int(effective_limits.get("max_changed_files_total") or request.max_changed_files_total)
        if self._stop_requested(request.pool_id, orchestrator_run_id):
            return self._stopped_result(out, request.pool_id, run_id, orchestrator_run_id)
        requested_item_ids = self._dependency_ready_item_ids(request, pool)
        autopilot = self._run_interleaved_items(
            request=request,
            out=out,
            run_id=run_id,
            orchestrator_run_id=orchestrator_run_id,
            requested_item_ids=requested_item_ids,
            project_path=str(preflight.get("effective_project_path") or request.project_path),
            effective_max_actions=effective_max_actions,
            effective_max_items=effective_max_items,
            effective_max_runtime_seconds=effective_max_runtime_seconds,
            effective_max_changed_files_total=effective_max_changed_files_total,
        )
        out.autopilot_result = autopilot.model_dump()
        out.stop_reason = autopilot.stop_reason
        for w in autopilot.warnings:
            if w not in out.warnings:
                out.warnings.append(w)
        # Post-apply Twin gate over the run's real verification evidence and changed files.
        # A NG outcome does NOT stop the run: the stop reason is fed back as Repair Compass
        # guidance and the affected items are regenerated (bounded). Only a genuine hard
        # boundary that persists after the bounded repair attempts is a safety stop.
        self._twin_post_apply_gate(out, request, autopilot)
        _post = (out.metadata.get("twin_control_plane") or {}).get("post_apply") or {}
        _ng, _ = self._twin_genuine_ng(_post)
        twin_post_block = ""
        if _ng:
            autopilot, twin_post_block = self._maybe_twin_repair(
                out=out, request=request, run_id=run_id, orchestrator_run_id=orchestrator_run_id,
                requested_item_ids=requested_item_ids, project_path=str(preflight.get("effective_project_path") or request.project_path),
                autopilot=autopilot,
                limits={"effective_max_actions": effective_max_actions,
                        "effective_max_items": effective_max_items,
                        "effective_max_runtime_seconds": effective_max_runtime_seconds,
                        "effective_max_changed_files_total": effective_max_changed_files_total})
            out.autopilot_result = autopilot.model_dump()
            out.stop_reason = autopilot.stop_reason
        if twin_post_block and resolve_gate_blocking():
            out.phase = "failure_analysis"
            out.status = "blocked_safety_review"
            out.stop_reason = twin_post_block
            self._emit("autonomous_codegen_blocked_twin_post_apply", request.pool_id, run_id, orchestrator_run_id, status=out.status, reason=out.stop_reason)
            self.save_result(out)
            return out
        repair_evidence = self._build_repairable_verification_evidence(request, autopilot)
        # Close the eval->profile->injection loop: record this run's control-plane capability
        # evidence (after the repair loop resolved) so future runs' Twin injection reflects it.
        _req_md = request.metadata or {}
        self._update_capability_profile_from_run(
            (out.metadata.get("twin_control_plane") or {}).get("post_apply") or {},
            model_id=str(_req_md.get("model_id") or _req_md.get("forge_model_id") or ""),
            provider_id=str(_req_md.get("provider_id") or _req_md.get("forge_provider_id") or ""),
            repair_attempts=out.metadata.get("twin_repair_attempts"))

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
                "llm_usage": dict(self.llm_usage),
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

    def _dependency_ready_item_ids(self, request: AtlasAutonomousCodegenRequest, pool) -> list[str]:
        if request.item_ids:
            return list(request.item_ids)
        try:
            ready = pool.get_ready_items()
        except Exception:
            ready = []
        if ready:
            return [item.item_id for item in ready]
        return [item.item_id for item in getattr(pool, "items", []) or []]

    def _run_interleaved_items(
        self,
        *,
        request: AtlasAutonomousCodegenRequest,
        out: AtlasAutonomousCodegenResult,
        run_id: str,
        orchestrator_run_id: str,
        requested_item_ids: list[str],
        project_path: str,
        effective_max_actions: int,
        effective_max_items: int,
        effective_max_runtime_seconds: int,
        effective_max_changed_files_total: int,
    ) -> AtlasMultiItemAutopilotResult:
        selected_ids = list(requested_item_ids)[: max(0, min(effective_max_items, effective_max_actions))]
        aggregate = AtlasMultiItemAutopilotResult(
            pool_id=request.pool_id,
            run_id=run_id,
            autopilot_run_id=f"auto_interleaved_{uuid4().hex[:10]}",
            policy_id=request.policy_id,
            status="completed",
            created_at=datetime.now(timezone.utc).isoformat(),
            metadata={"mode": "interleaved_generate_apply_verify", "sub_runs": [], "revision_regenerations": []},
        )
        changed_total = 0
        no_content_item_ids: list[str] = []

        # Under full-auto (autonomous bounded-dev envelope) a successfully-applied change must not be
        # paused by the evaluator's conservative `manual_required` (e.g. a static file whose only
        # verification is "open in a browser" and therefore cannot auto-pass). Autonomy means such
        # non-critical decisions auto-continue; critical/protected/destructive events still pause via
        # the separate critical-event path. Supervised modes keep the manual-review stop.
        base_pool = self.storage.load_pool(request.pool_id)
        is_full_auto = is_full_auto_context(
            preset_id=str((request.metadata or {}).get("preset_id") or ""),
            automation_level=str(getattr(base_pool, "automation_level", "") or ""),
        )
        stop_on_manual_required = not is_full_auto

        for index, item_id in enumerate(selected_ids):
            if self._stop_requested(request.pool_id, orchestrator_run_id):
                aggregate.status = "stopped"
                aggregate.stop_reason = "user_stop_requested"
                break
            pool = self.storage.load_pool(request.pool_id)
            item = pool.get_item(item_id)
            if item is None:
                aggregate.item_results.append(AtlasAutopilotItemResult(item_id=item_id, status="skipped", reason="item_not_found"))
                aggregate.skipped_count += 1
                continue
            normalize_plan_item_file_changes(item)
            if self._is_hard_blocked_item(item):
                out.skipped_generation_count += 1
                no_content_item_ids.append(item_id)
                out.proposal_results.append(AtlasAutonomousCodegenProposalResult(item_id=item_id, status="skipped", reason="hard_blocked_item"))
                aggregate.item_results.append(AtlasAutopilotItemResult(item_id=item_id, status="blocked", reason="hard_blocked_item"))
                aggregate.blocked_count += 1
                continue

            out.phase = "candidate_generation"
            self._progress(
                request.pool_id,
                run_id,
                orchestrator_run_id,
                phase=out.phase,
                current_item_index=index,
                total_items=len(selected_ids),
                sub_phase="patch_generation",
                last_event="patch_generation_item_started",
            )
            stale = self._proposal_revision_mismatch(item, project_path=project_path)
            if stale:
                self._clear_patch_content(item)
                item.metadata.setdefault("patch_proposal_revision_mismatches", []).append(stale)
                self.storage.save_pool(pool)
                aggregate.metadata["revision_regenerations"].append({"item_id": item_id, **stale})
                self._progress(
                    request.pool_id,
                    run_id,
                    orchestrator_run_id,
                    phase=out.phase,
                    current_item_index=index,
                    total_items=len(selected_ids),
                    sub_phase="revision_precondition_mismatch",
                    last_event="patch_generation_regenerating_stale_proposal",
                    item_id=item_id,
                )

            if request.generate_missing_patches and (stale or not self._item_has_patch_content(item)):
                pres = self.patch_proposal_service.propose_for_item(
                    AtlasPatchProposalRequest(
                        pool_id=request.pool_id,
                        item_id=item_id,
                        run_id=run_id,
                        workspace_id=request.workspace_id,
                        source_type="plan_item",
                        metadata=self._twin_generation_hints(out),
                    )
                )
                available = is_patch_generation_success((pres.metadata or {}).get("patch_generation"))
                reason = "" if available else (pres.warnings[0] if pres.warnings else "patch_content_unavailable")
                out.proposal_results.append(
                    AtlasAutonomousCodegenProposalResult(
                        item_id=item_id,
                        status=pres.status if available else "no_content",
                        patch_content_available=available,
                        reason=reason,
                    )
                )
                if available:
                    out.generated_count += 1
                else:
                    out.skipped_generation_count += 1
                    no_content_item_ids.append(item_id)
                    aggregate.item_results.append(AtlasAutopilotItemResult(item_id=item_id, status="blocked", reason="patch_content_unavailable"))
                    aggregate.blocked_count += 1
                    continue
            elif self._item_has_patch_content(item):
                out.skipped_generation_count += 1

            pool = self.storage.load_pool(request.pool_id)
            item = pool.get_item(item_id)
            if item is None or not self._item_has_patch_content(item):
                no_content_item_ids.append(item_id)
                aggregate.item_results.append(AtlasAutopilotItemResult(item_id=item_id, status="blocked", reason="patch_content_unavailable"))
                aggregate.blocked_count += 1
                continue

            out.phase = "candidate_apply"
            self._progress(
                request.pool_id,
                run_id,
                orchestrator_run_id,
                phase=out.phase,
                current_item_index=index,
                total_items=len(selected_ids),
                sub_phase="candidate_apply",
                last_event="candidate_apply_started",
            )
            sub_run = self.multi_item_autopilot_service.run(
                AtlasMultiItemAutopilotRequest(
                    pool_id=request.pool_id,
                    run_id=run_id,
                    workspace_id=request.workspace_id,
                    project_path=project_path,
                    item_ids=[item_id],
                    policy_id=request.policy_id,
                    require_approval=False,
                    stop_on_manual_required=stop_on_manual_required,
                    max_items=1,
                    max_runtime_seconds=effective_max_runtime_seconds,
                    max_changed_files_total=max(0, effective_max_changed_files_total - changed_total),
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
                        "interleaved_parent_autopilot_run_id": aggregate.autopilot_run_id,
                    },
                )
            )
            aggregate.metadata["sub_runs"].append(
                {
                    "item_id": item_id,
                    "autopilot_run_id": sub_run.autopilot_run_id,
                    "status": sub_run.status,
                    "stop_reason": sub_run.stop_reason,
                }
            )
            self._merge_item_autopilot_result(aggregate, sub_run)
            self._persist_completed_item_evidence(request.pool_id, sub_run)
            changed_total = len(self._changed_files_from_autopilot(aggregate))
            if sub_run.status in {"stopped", "failed", "blocked", "needs_revision"}:
                aggregate.status = sub_run.status
                aggregate.stop_reason = sub_run.stop_reason
                break
            if sub_run.status == "partial" and aggregate.status == "completed":
                aggregate.status = "partial"

        if aggregate.processed_count == 0 and no_content_item_ids:
            aggregate.status = "no_content"
            aggregate.stop_reason = "no_patch_content"
            aggregate.metadata["no_content_item_ids"] = sorted(set(no_content_item_ids))
        if aggregate.status == "completed" and aggregate.completed_count == 0 and aggregate.blocked_count > 0:
            aggregate.status = "blocked"
        if aggregate.status in {"stopped", "failed", "blocked", "needs_revision"} and aggregate.completed_count > 0:
            aggregate.status = "partial"
        self._emit(
            "autonomous_codegen_interleaved_completed",
            request.pool_id,
            run_id,
            orchestrator_run_id,
            status=aggregate.status,
            generated_count=out.generated_count,
            skipped_count=out.skipped_generation_count,
        )
        return aggregate

    def _merge_item_autopilot_result(self, aggregate: AtlasMultiItemAutopilotResult, sub_run: AtlasMultiItemAutopilotResult) -> None:
        aggregate.processed_count += int(getattr(sub_run, "processed_count", 0) or 0)
        aggregate.completed_count += int(getattr(sub_run, "completed_count", 0) or 0)
        aggregate.applied_no_verification_count += int(getattr(sub_run, "applied_no_verification_count", 0) or 0)
        aggregate.skipped_count += int(getattr(sub_run, "skipped_count", 0) or 0)
        aggregate.blocked_count += int(getattr(sub_run, "blocked_count", 0) or 0)
        aggregate.failed_count += int(getattr(sub_run, "failed_count", 0) or 0)
        aggregate.item_results.extend(list(getattr(sub_run, "item_results", []) or []))
        for warning in getattr(sub_run, "warnings", []) or []:
            if warning not in aggregate.warnings:
                aggregate.warnings.append(warning)
        for error in getattr(sub_run, "errors", []) or []:
            if error not in aggregate.errors:
                aggregate.errors.append(error)

    def _persist_completed_item_evidence(self, pool_id: str, sub_run: AtlasMultiItemAutopilotResult) -> None:
        if not sub_run.item_results:
            return
        pool = self.storage.load_pool(pool_id)
        changed = False
        for result in sub_run.item_results:
            item = pool.get_item(result.item_id)
            if item is None:
                continue
            item.metadata.setdefault("last_autopilot_result", result.model_dump())
            if result.verification_result:
                item.metadata["last_verification_result"] = dict(result.verification_result)
            if result.status == "completed":
                item.status = "completed"
                if item.item_id not in pool.completed_item_ids:
                    pool.completed_item_ids.append(item.item_id)
                item.metadata.setdefault("safe_apply", {})
                if result.changed_files:
                    item.metadata["safe_apply"]["changed_files"] = list(result.changed_files)
            changed = True
        if changed:
            self.storage.save_pool(pool)
            try:
                self.journal.save_plan_pool(pool)
            except Exception:
                pass

    def _proposal_revision_mismatch(self, item, *, project_path: str) -> dict[str, Any]:
        expected = self._proposal_base_file_revisions(item)
        if not expected:
            return {}
        current = self._current_file_revisions(project_path=project_path, item=item)
        mismatches = {
            path: {"expected": expected_rev, "actual": current.get(path, "absent")}
            for path, expected_rev in expected.items()
            if current.get(path, "absent") != expected_rev
        }
        return {"reason": "base_file_revision_mismatch", "mismatches": mismatches} if mismatches else {}

    @staticmethod
    def _proposal_base_file_revisions(item) -> dict[str, str]:
        md = item.metadata or {}
        patch_proposal = md.get("patch_proposal") if isinstance(md.get("patch_proposal"), dict) else {}
        proposal_md = patch_proposal.get("metadata") if isinstance(patch_proposal.get("metadata"), dict) else {}
        raw = proposal_md.get("base_file_revisions") or patch_proposal.get("base_file_revisions") or md.get("base_file_revisions") or {}
        if not isinstance(raw, dict):
            return {}
        return {str(path): str(rev or "absent") for path, rev in raw.items() if str(path).strip()}

    def _current_file_revisions(self, *, project_path: str, item) -> dict[str, str]:
        root = Path(project_path or "").resolve()
        revisions: dict[str, str] = {}
        for rel in self._item_revision_paths(item):
            try:
                path = PurePosixPath(rel)
                if path.is_absolute() or ".." in path.parts:
                    revisions[rel] = "unsafe"
                    continue
                target = (root / Path(*path.parts)).resolve()
                target.relative_to(root)
                if not target.is_file():
                    revisions[rel] = "absent"
                    continue
                text = target.read_text(encoding="utf-8", errors="replace")
                revisions[rel] = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
            except Exception:
                revisions[rel] = "unreadable"
        return revisions

    @staticmethod
    def _item_revision_paths(item) -> list[str]:
        paths: list[str] = []
        for path in getattr(item, "target_files", []) or []:
            text = str(path).replace("\\", "/").strip()
            if text and text not in paths:
                paths.append(text)
        md = item.metadata or {}
        file_changes = md.get("file_changes") if isinstance(md.get("file_changes"), list) else []
        for change in file_changes:
            if not isinstance(change, dict):
                continue
            text = str(change.get("path") or "").replace("\\", "/").strip()
            if text and text not in paths:
                paths.append(text)
        return paths

    @staticmethod
    def _clear_patch_content(item) -> None:
        md = item.metadata or {}
        for key in ("proposed_content", "content", "patch", "unified_diff_preview", "edits", "file_changes"):
            md.pop(key, None)
        patch_proposal = md.get("patch_proposal") if isinstance(md.get("patch_proposal"), dict) else {}
        for key in ("proposed_content", "content", "patch", "unified_diff_preview", "edits", "file_changes"):
            patch_proposal.pop(key, None)
        if patch_proposal:
            patch_proposal["status"] = "stale_base_revision"
            md["patch_proposal"] = patch_proposal

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

    def _ensure_forge_model_identity(self, request: AtlasAutonomousCodegenRequest) -> AtlasAutonomousCodegenRequest:
        """Attach a Forge-evaluated model identity (provider_id/model_id) to the run when the
        caller did not supply one, so capability-profile-driven adaptation (route selection,
        decomposition tier, learned evidence) is active instead of neutral. Identity only — this
        never changes execution routing (an active cutover stays an explicit Stage Matrix act).
        Guarded: any failure leaves the request unchanged (legacy neutral behaviour)."""
        md = dict(request.metadata or {})
        if str(md.get("model_id") or md.get("forge_model_id") or "").strip():
            return request  # caller already pinned the model; respect it.
        try:
            import os
            from agent.model_forge.forge_service import ForgeService

            # Live-probe the local server (e.g. :8080) only when explicitly opted in, since it
            # makes a network call; default runs stay fast and resolve from Forge config alone.
            probe_live = os.environ.get("ATLAS_FORGE_PROBE_LOCAL", "").strip().lower() in {"1", "on", "true", "yes"}
            resolved = ForgeService(self.data_root, env=os.environ).resolve_active_codegen_model(probe_live=probe_live)
            model_id = str(resolved.get("model_id") or "").strip()
            if not model_id:
                return request
            md["model_id"] = model_id
            md["provider_id"] = str(resolved.get("provider_id") or "")
            md["forge_model_resolution"] = resolved
            return request.model_copy(update={"metadata": md})
        except Exception:  # noqa: BLE001 - identity attachment is advisory; never break the run.
            return request

    def _attach_twin_control_plane(self, out: AtlasAutonomousCodegenResult, request: AtlasAutonomousCodegenRequest, pool: AtlasPlanPool) -> str:
        """Attach Twin/Forge pipeline evidence to the run metadata and return a block
        reason when the (promoted) blocking gate must stop the run, else "".

        Fully guarded: it never raises and never mutates the pool. The seam stays
        advisory for execution authority — Atlas keeps Proposal / Safe Apply /
        Verification. Blocking, when enabled, is limited to a genuine policy prerequisite
        (active engaged without assembled shadow evidence) and never blocks on advisory
        uncertainty or on an internal/infra error."""
        try:
            mode = resolve_pipeline_mode()
            changed_refs: list[str] = []
            for item in getattr(pool, "items", []) or []:
                for change in normalize_plan_item_file_changes(item) or []:
                    path = change.get("path") if isinstance(change, dict) else None
                    if path:
                        changed_refs.append(str(path))
                # Pre-flight (before generation) has no file_changes yet; fall back to the
                # plan item's target files so impact/evidence can be derived.
                for tf in getattr(item, "target_files", []) or []:
                    if tf:
                        changed_refs.append(str(tf))
            # Project Twin: auto-build from the live project BEFORE generation so impact / Safe-Edit
            # Briefing (who depends on what we change) is available THIS run — the dependency-awareness
            # that lifts a weak model on a large existing codebase. Default ON in active mode
            # (ATLAS_TWIN_AUTOBUILD=off to disable); the explicit ATLAS_TWIN_BUILD_PROJECT flag also
            # forces it in any mode. Built once per run and cached; never raises; falls back to the
            # legacy load-only path when autobuild is off. Disabled-safe.
            twin_store = self.project_twin_store
            if twin_store is None:
                _twin_pid = str(request.pool_id or getattr(pool, "project_id", "") or "")
                _twin_path = str(request.project_path or getattr(pool, "project_path", "") or "")
                if _twin_path and (resolve_build_project_twin() or (mode == PipelineMode.ACTIVE and resolve_twin_autobuild())):
                    twin_store = ensure_project_twin(
                        data_root=str(self.data_root), project_id=_twin_pid, project_path=_twin_path)
                elif resolve_build_project_twin():
                    twin_store = load_project_twin_store(data_root=str(self.data_root), project_id=_twin_pid)
                self.project_twin_store = twin_store
            # Expand changed FILE paths to the Twin's symbol refs so impact (callers) is non-empty —
            # the Twin seeds impact on symbols, not bare file paths.
            _twin_project_id = str(request.pool_id or getattr(pool, "project_id", "") or "")
            impact_refs = expand_changed_refs_to_symbols(twin_store, _twin_project_id, changed_refs)
            impact = try_project_twin_impact(
                project_id=_twin_project_id,
                changed_refs=impact_refs,
                store=twin_store,
            )
            req_md = request.metadata or {}
            evidence = build_twin_pipeline_evidence(
                mode=mode,
                requirement=str(request.user_requirement or ""),
                pool_id=str(request.pool_id or ""),
                project_path=str(request.project_path or getattr(pool, "project_path", "") or ""),
                changed_refs=changed_refs,
                item_refs=[str(getattr(item, "item_id", "")) for item in getattr(pool, "items", []) or []],
                impact=impact,
                model_id=str(req_md.get("model_id") or req_md.get("forge_model_id") or ""),
                provider_id=str(req_md.get("provider_id") or req_md.get("forge_provider_id") or ""),
                profile_store_dir=str(Path(self.data_root) / "model_forge" / "profiles"),
                anti_pattern_memory=self._load_anti_pattern_memory(),
                golden_index=self._load_golden_index(),
            )
            block_reason = twin_gate_block_reason(evidence) if resolve_gate_blocking() else ""
            evidence["gate_blocking_enabled"] = resolve_gate_blocking()
            evidence["gate_blocked"] = bool(block_reason)
            # Capture the BEFORE schema (advisory Schema Guardian) of the target files as they
            # exist pre-generation, so a post-apply diff can be measured.
            try:
                project_path = str(request.project_path or getattr(pool, "project_path", "") or "")
                before = python_schema_snapshot(project_path, changed_refs, schema_id="before")
                self._twin_before_schema = before.model_dump(mode="json") if before is not None else None
            except Exception:
                self._twin_before_schema = None
            out.metadata["twin_control_plane"] = evidence
            return block_reason
        except Exception as exc:  # pragma: no cover - defensive: never break the legacy flow
            out.metadata["twin_control_plane"] = {
                "mode": "off", "engaged": False, "available": False,
                "reason": f"twin_seam_error:{type(exc).__name__}",
            }
            return ""  # an internal seam error is never a hard block (unavailable != failed)

    @staticmethod
    def _twin_generation_hints(out: AtlasAutonomousCodegenResult) -> dict[str, Any]:
        """Forge Twin route-selection hints for patch generation. Advisory: the generator
        may use the recommended route/instruction style; it does not override Atlas's own
        route/safety logic. Empty when the seam is off/unavailable."""
        tcp = (out.metadata or {}).get("twin_control_plane") or {}
        if not tcp.get("available") or tcp.get("mode") == "off":
            return {}
        seb = tcp.get("safe_edit_briefing") or {}
        dependent_files = list(seb.get("dependent_files") or []) if isinstance(seb, dict) else []
        hints = {
            "twin_route": tcp.get("route"),
            "twin_instruction_style": tcp.get("instruction_style"),
            "twin_injection_level": tcp.get("twin_injection_level"),
            "twin_policy_id": tcp.get("policy_id"),
            # The compiled Twin instruction, used by the generator as a bounded control section.
            "twin_instruction": tcp.get("compiled_instruction"),
            "twin_instruction_id": tcp.get("instruction_id"),
            # Files the Twin found depend on this change — generation ranks/loads their symbols so the
            # model edits with the dependents' real API in view (A6: impact-driven context selection).
            "impacted_dependent_files": dependent_files or None,
        }
        return {"twin_generation_hints": {k: v for k, v in hints.items() if v is not None}}

    def _anti_pattern_store(self):
        from agent.twin_control_plane.anti_pattern_memory import AntiPatternMemoryStore
        return AntiPatternMemoryStore(Path(self.data_root) / "twin_control_plane" / "anti_pattern_memory")

    def _load_anti_pattern_memory(self):
        """Load the durable Anti-Pattern memory so prior-run guardrails advise this run.
        Returns None on any error (advisory injection then degrades to empty)."""
        try:
            return self._anti_pattern_store().load()
        except Exception:  # pragma: no cover - defensive
            return None

    def _update_capability_profile_from_run(self, report: dict, *, model_id: str, provider_id: str, repair_attempts=None) -> None:
        """Close the eval->profile->injection loop: derive control-plane capability evidence
        from THIS run's outcome and record it to the ProfileStore, keyed by the model. Only
        runs with a known model_id contribute (no anonymous attribution). Conservative,
        evidence-backed dimensions only:
        - contract_preservation: a hard-boundary block lowers it, a clean run raises it;
        - test_generation: failed verification lowers it, passed raises it;
        - repair_discipline: a recovered repair loop raises it, an exhausted one lowers it.
        Pure evidence gaps (unavailable) contribute nothing (unavailable != failure)."""
        try:
            if not model_id or not isinstance(report, dict) or not report.get("ran"):
                return
            dims: dict[str, float] = {}
            repair_reasons = report.get("repair_reasons") or []
            blocked = bool(report.get("blocked_reasons"))
            passed = bool(report.get("passed_evidence"))
            failed_verif = "verification_failed" in repair_reasons
            if blocked:
                dims["contract_preservation"] = 0.0
            elif passed:
                dims["contract_preservation"] = 1.0
            if failed_verif:
                dims["test_generation"] = 0.0
            elif passed:
                dims["test_generation"] = 1.0
            if isinstance(repair_attempts, list) and repair_attempts:
                dims["repair_discipline"] = 0.0 if repair_attempts[-1].get("still_ng") else 1.0
            if not dims:
                return
            from agent.model_forge.profile_store import ProfileStore
            store = ProfileStore(Path(self.data_root) / "model_forge" / "profiles")
            store.record_observation(
                model_id=model_id, provider_id=provider_id or "local", dimensions=dims,
                source="autonomous_run",
                evidence_refs=[str((report.get("ledger_entry") or {}).get("entry_id") or report.get("report_id") or "")])
        except Exception:  # pragma: no cover - defensive
            return

    def _golden_patch_store(self):
        from agent.model_forge.golden_patch_retrieval import GoldenPatchStore
        return GoldenPatchStore(Path(self.data_root) / "twin_control_plane" / "golden_patches")

    def _load_golden_index(self):
        """Load durable accepted golden patches as an advisory retrieval index (or None)."""
        try:
            return self._golden_patch_store().load_index()
        except Exception:  # pragma: no cover - defensive
            return None

    def _persist_golden_patch(self, report: dict) -> None:
        """On an accepted decision, persist the patch as a durable golden example for later
        advisory retrieval. Guarded; only accepted patches are stored."""
        try:
            if not isinstance(report, dict) or report.get("decision") != "accepted":
                return
            entry = report.get("ledger_entry") or {}
            tcp = None  # route comes from the pre-flight evidence
            from agent.model_forge.golden_patch_retrieval import GoldenPatch
            from agent.model_forge.route_taxonomy import ForgeRoute
            route = None
            try:
                route = ForgeRoute(report.get("route")) if report.get("route") else None
            except Exception:
                route = None
            patch = GoldenPatch(
                patch_id=str(entry.get("entry_id") or report.get("report_id") or "patch"),
                task_category="autonomous_codegen", route=route,
                model_id=str(entry.get("model_id") or ""), provider_id=str(entry.get("provider_id") or ""),
                affected_refs=list(report.get("passed_evidence") or []),
                proof_outcome="accepted", summary="accepted autonomous codegen patch",
                evidence_refs=[str(entry.get("entry_id") or "")])
            self._golden_patch_store().add(patch)
        except Exception:  # pragma: no cover - defensive
            return

    def _persist_proof_ledger_entry(self, report: dict) -> None:
        """Durably persist the post-apply Proof Ledger entry and, for non-accepted
        decisions, feed the Anti-Pattern memory so later runs receive evidence-backed
        guardrails. Guarded — never breaks the run."""
        try:
            entry_dump = report.get("ledger_entry") if isinstance(report, dict) else None
            if not entry_dump:
                return
            from agent.twin_control_plane.proof_ledger import ProofLedgerEntry, ProofLedgerStore
            from agent.twin_control_plane.anti_pattern_memory import record_from_proof_ledger
            entry = ProofLedgerEntry.model_validate(entry_dump)
            ProofLedgerStore(Path(self.data_root) / "twin_control_plane" / "proof_ledger").append(entry)
            # Cross-run learning: only a GENUINE product regression (failed verification) or a
            # hard-boundary block becomes an evidence-bound anti-pattern. Pure evidence gaps
            # (twin_revision_evidence_missing, verification_unavailable/missing) are NOT recorded
            # — unavailable is not a failure — so accepted/evidence-thin runs add no false guardrail.
            product_regression = "verification_failed" in entry.repair_reasons
            hard_boundary = bool(entry.blocked_reasons)
            if product_regression or hard_boundary:
                reasons = entry.blocked_reasons if hard_boundary else ["verification_failed"]
                store = self._anti_pattern_store()
                memory = record_from_proof_ledger(
                    store.load(), entry,
                    pattern_id=f"apm:{'blocked' if hard_boundary else 'regression'}:{','.join(sorted(reasons))[:48]}",
                    title=f"{'hard-boundary' if hard_boundary else 'product-regression'} pattern from autonomous run",
                    categories=list(reasons),
                    confidence=0.6, model_id=entry.model_id,
                )
                store.save(memory)
        except Exception:  # pragma: no cover - defensive
            return

    @staticmethod
    def _twin_state_observations(autopilot, project_path: str, changed_files: list[str]):
        """Produce best-effort StateMirror observations: per-item verification (runtime
        surface) and post-apply file existence (persistence surface). Real, coarse evidence —
        never fabricated. Returns (runtime_observations, persisted_observations)."""
        from agent.twin_control_plane.state_mirror import StateObservation, StateSurface
        runtime: list[StateObservation] = []
        persisted: list[StateObservation] = []
        try:
            for it in getattr(autopilot, "item_results", []) or []:
                vr = getattr(it, "verification_result", None) or {}
                status = str(vr.get("status") or "unavailable")
                ev_status = status if status in {"passed", "failed", "unavailable"} else "observed"
                runtime.append(StateObservation(
                    path=f"runtime.verification.{getattr(it, 'item_id', '')}", value=status,
                    surface=StateSurface.RUNTIME, evidence_status=ev_status, authoritative=True))
            for rel in changed_files or []:
                exists = bool(project_path) and (Path(project_path) / str(rel)).exists()
                persisted.append(StateObservation(
                    path=f"persistence.{rel}", value=exists, surface=StateSurface.PERSISTENCE,
                    evidence_status="passed" if exists else "failed", authoritative=True))
        except Exception:  # pragma: no cover - defensive
            return [], []
        return runtime, persisted

    @staticmethod
    def _twin_attempted_actions(request: AtlasAutonomousCodegenRequest) -> list[str]:
        """Map request-level signals to Contract Sentinel attempted-action tokens so the
        gate can hard-block genuine boundary attempts (remote publish, test weakening,
        Safe Apply bypass). Conservative: only explicit signals are surfaced."""
        actions: list[str] = []
        md = request.metadata or {}
        signal = {str(s).strip().lower() for s in (md.get("twin_attempted_actions") or [])}
        for token in ("bypass_safe_apply", "direct_workspace_write", "remote_publish",
                      "remote_mutation", "create_pr", "weaken_test", "delete_stale_test"):
            if token in signal:
                actions.append(token)
        return actions

    def _clear_affected_items(self, pool_id: str, autopilot) -> None:
        """Clear patch content for the items in this autopilot result so they regenerate."""
        pool = self.storage.load_pool(pool_id)
        changed = False
        for it in getattr(autopilot, "item_results", []) or []:
            item = pool.get_item(getattr(it, "item_id", ""))
            if item is not None:
                self._clear_patch_content(item)
                changed = True
        if changed:
            self.storage.save_pool(pool)

    @staticmethod
    def _twin_genuine_ng(report: dict) -> tuple[bool, bool]:
        """Return ``(is_ng, is_hard)`` for a post-apply report. A genuine NG is only a real
        product regression (failed verification) or a hard-boundary block — NOT an evidence
        gap (missing twin revision / unavailable verification). Evidence gaps never trigger
        regeneration or a stop."""
        hard = bool(report.get("blocked_reasons"))
        failed = "verification_failed" in (report.get("repair_reasons") or [])
        return (hard or failed), hard

    def _maybe_twin_repair(
        self, *, out: AtlasAutonomousCodegenResult, request: AtlasAutonomousCodegenRequest,
        run_id: str, orchestrator_run_id: str, requested_item_ids: list[str], project_path: str,
        autopilot, limits: dict,
    ):
        """Twin gate NG -> inject Repair Compass feedback and REGENERATE the affected items
        (bounded by max_retries), re-evaluating the gate each pass. The run is NOT stopped on
        a recoverable NG; the stop reason is fed back so the model regenerates to eliminate
        it. Returns ``(autopilot, final_block_reason)`` where final_block_reason is non-empty
        only when a genuine hard boundary persists after the bounded attempts."""
        report = ((out.metadata.get("twin_control_plane") or {}).get("post_apply") or {})
        _, hard = self._twin_genuine_ng(report)
        guidance = report.get("repair_guidance") or ""
        max_attempts = max(1, int(getattr(request, "max_retries", 0) or 2))
        for attempt in range(1, max_attempts + 1):
            if not guidance:
                break
            new_md = dict(request.metadata or {})
            hints = dict(new_md.get("twin_generation_hints") or {})
            hints["twin_repair_section"] = guidance
            new_md["twin_generation_hints"] = hints
            repair_request = request.model_copy(update={"metadata": new_md})
            self._clear_affected_items(request.pool_id, autopilot)
            self._emit("autonomous_codegen_twin_repair_started", request.pool_id, run_id,
                       orchestrator_run_id, attempt=attempt)
            autopilot = self._run_interleaved_items(
                request=repair_request, out=out, run_id=run_id,
                orchestrator_run_id=orchestrator_run_id, requested_item_ids=requested_item_ids,
                project_path=project_path, **limits)
            out.autopilot_result = autopilot.model_dump()
            self._twin_post_apply_gate(out, request, autopilot)
            report = ((out.metadata.get("twin_control_plane") or {}).get("post_apply") or {})
            ng, hard = self._twin_genuine_ng(report)
            guidance = report.get("repair_guidance") or ""
            (out.metadata.setdefault("twin_repair_attempts", [])).append(
                {"attempt": attempt, "decision": report.get("decision"), "still_ng": ng})
            self._emit("autonomous_codegen_twin_repair_completed", request.pool_id, run_id,
                       orchestrator_run_id, attempt=attempt, decision=report.get("decision"))
            if not ng:
                return autopilot, ""  # the stop reason was eliminated by regeneration
        # Exhausted. Only a persistent genuine hard boundary remains a safety stop; a
        # recoverable NG (needs_repair) does not halt the run.
        return autopilot, ("twin_post_apply_hard_boundary" if hard else "")

    def _twin_post_apply_gate(self, out: AtlasAutonomousCodegenResult, request: AtlasAutonomousCodegenRequest, autopilot) -> str:
        """Run the post-apply Twin Patch Impact Gate over the run's REAL verification
        evidence and changed files; record it and return a block reason when the
        (promoted) blocking gate must stop acceptance, else "".

        Fully guarded and advisory for execution authority: Atlas keeps Verification /
        Repair. Blocking is conservative (genuine hard boundary, or the opt-in
        unverified-change case)."""
        try:
            mode = resolve_pipeline_mode()
            if mode == PipelineMode.OFF:
                return ""
            changed_files = self._changed_files_from_autopilot(autopilot)
            verification: list[dict[str, str]] = []
            for item in getattr(autopilot, "item_results", []) or []:
                vr = getattr(item, "verification_result", None) or {}
                verification.append({
                    "evidence_id": f"verify_{getattr(item, 'item_id', '')}",
                    "status": str(vr.get("status") or "unavailable"),
                })
            impact = try_project_twin_impact(
                project_id=str(request.pool_id or ""), changed_refs=changed_files,
                store=self.project_twin_store,
            )
            # Capture the AFTER schema and run advisory Schema Guardian against the BEFORE
            # snapshot captured at pre-flight. StateMirror stays unavailable (no runtime state
            # observations are produced by the codegen path). Advisory only — never blocks.
            after_schema = None
            try:
                project_path = str(request.project_path or "")
                snap = python_schema_snapshot(project_path, changed_files, schema_id="after")
                after_schema = snap.model_dump(mode="json") if snap is not None else None
            except Exception:
                after_schema = None
            from agent.twin_control_plane.schema_guardian import SchemaSnapshot
            before_dump = getattr(self, "_twin_before_schema", None)
            before_schema = SchemaSnapshot.model_validate(before_dump) if before_dump else None
            after_obj = SchemaSnapshot.model_validate(after_schema) if after_schema else None
            # StateMirror observation sources: per-file verification (runtime surface) and
            # post-apply file existence (persistence surface). Coarse but real — no fabrication.
            runtime_state, persisted_state = self._twin_state_observations(autopilot, str(request.project_path or ""), changed_files)
            req_md = request.metadata or {}
            report = evaluate_twin_post_apply(
                mode=mode,
                blocking=resolve_gate_blocking(),
                block_unverified=resolve_block_unverified(),
                requirement=str(request.user_requirement or ""),
                pool_id=str(request.pool_id or ""),
                project_path=str(request.project_path or ""),
                changed_files=changed_files,
                verification=verification,
                impact=impact,
                attempted_actions=self._twin_attempted_actions(request),
                after_twin_revision_id=getattr(autopilot, "autopilot_run_id", ""),
                requirement_ref=str(request.pool_id or ""),
                plan_item_ref=str(request.run_id or ""),
                model_id=str(req_md.get("model_id") or req_md.get("forge_model_id") or ""),
                provider_id=str(req_md.get("provider_id") or req_md.get("forge_provider_id") or ""),
                before_schema=before_schema, after_schema=after_obj,
                runtime_state=runtime_state, persisted_state=persisted_state,
                block_schema=resolve_block_schema(),
            )
            tcp = out.metadata.get("twin_control_plane")
            if isinstance(tcp, dict):
                report["route"] = tcp.get("route")  # carry the selected route for golden-patch indexing
                tcp["post_apply"] = report
            else:
                out.metadata["twin_control_plane"] = {"post_apply": report}
            self._persist_proof_ledger_entry(report)
            self._persist_golden_patch(report)
            # Refresh the persistent Project Twin from the project after applying changes so the next
            # item/run sees up-to-date impact/blast-map evidence. Runs when autobuild is on (active
            # mode, default) or the explicit build flag is set; guarded and never breaks the flow.
            if changed_files and (resolve_build_project_twin() or resolve_twin_autobuild()):
                project_path = str(request.project_path or "")
                store = refresh_project_twin(
                    data_root=str(self.data_root),
                    project_id=str(request.pool_id or ""), project_path=project_path)
                if store is not None:
                    self.project_twin_store = store
            return report.get("block_reason") or ""
        except Exception as exc:  # pragma: no cover - defensive: never break the legacy flow
            return ""  # a post-apply seam error is never a hard block

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
            # "." is the project-root sentinel: it matches every repo-relative path under the
            # selected project's work root (used by the bounded-dev envelope to allow the whole
            # selected project while blocked_paths still guard dangerous locations).
            if pfx == ".":
                return True
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
