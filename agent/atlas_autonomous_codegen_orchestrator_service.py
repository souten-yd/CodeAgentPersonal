from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from agent.atlas_autonomous_codegen_orchestrator_schema import (
    AtlasAutonomousCodegenProposalResult,
    AtlasAutonomousCodegenRequest,
    AtlasAutonomousCodegenResult,
)
from agent.atlas_file_safe_apply_executor import normalize_safe_apply_action_type
from agent.atlas_multi_item_autopilot_schema import AtlasMultiItemAutopilotRequest
from agent.atlas_patch_proposal_schema import AtlasPatchProposalRequest
from agent.atlas_plan_item_file_changes import has_file_change_content, normalize_plan_item_file_changes

# Items the full-auto profile never applies; generating a patch for them is wasted work because
# the safe-apply gate (and atlas_full_auto_gate) hard-block them downstream anyway.
_HARD_BLOCK_ACTION_TYPES = {"delete", "run_command"}


class AtlasAutonomousCodegenOrchestratorService:
    """Compose plan -> batch patch generation -> multi-item apply into one autonomous call.

    This adds NO new gate logic: Phase 3 delegates to AtlasMultiItemAutopilotService, which already
    inherits the workstream-1 full_auto relaxation. The safety boundary is the plan-time critique
    gate (Phase 1 stop) plus the pre-apply snapshot/rollback inside the multi-item engine.
    """

    def __init__(self, *, storage, journal, patch_proposal_service, multi_item_autopilot_service):
        self.storage = storage
        self.journal = journal
        self.patch_proposal_service = patch_proposal_service
        self.multi_item_autopilot_service = multi_item_autopilot_service

    def run(self, request: AtlasAutonomousCodegenRequest) -> AtlasAutonomousCodegenResult:
        run_id = request.run_id or f"autocodegen_{uuid4().hex[:10]}"
        orchestrator_run_id = f"acg_{uuid4().hex[:10]}"
        out = AtlasAutonomousCodegenResult(
            pool_id=request.pool_id,
            run_id=run_id,
            orchestrator_run_id=orchestrator_run_id,
            status="running",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._emit("autonomous_codegen_started", request.pool_id, run_id, orchestrator_run_id, status="started")

        # ── Phase 0: load + tag the pool as full_autopilot ───────────────────────────────────
        pool = self.storage.load_pool(request.pool_id)
        if str(getattr(pool, "automation_level", "")) != "full_autopilot":
            pool.automation_level = "full_autopilot"
            self.storage.save_pool(pool)
        if not pool.items:
            out.phase, out.status, out.stop_reason = "completed", "no_items", "pool_has_no_items"
            self._emit("autonomous_codegen_completed", request.pool_id, run_id, orchestrator_run_id, status=out.status)
            return out

        # ── Phase 1: safety gate (the hard boundary the user agreed to keep) ──────────────────
        out.phase = "safety_gate"
        revision_required = bool((pool.metadata or {}).get("plan_revision_required"))
        approval_required = str(getattr(pool, "status", "")).lower() == "approval_required"
        if revision_required or approval_required:
            out.status = "blocked_safety_review"
            out.stop_reason = "plan_revision_required" if revision_required else "approval_required"
            self._emit("autonomous_codegen_blocked_safety_review", request.pool_id, run_id, orchestrator_run_id, status=out.status, reason=out.stop_reason)
            return out

        # ── Phase 2: batch first-patch generation for items lacking content ───────────────────
        out.phase = "patch_generation"
        if request.generate_missing_patches:
            ids = request.item_ids or [i.item_id for i in pool.items]
            for item_id in ids[: max(0, int(request.max_items))]:
                pool = self.storage.load_pool(request.pool_id)  # pick up content persisted so far
                item = pool.get_item(item_id)
                if item is None:
                    continue
                normalize_plan_item_file_changes(item)
                if self._item_has_patch_content(item):
                    out.skipped_generation_count += 1
                    continue
                if self._is_hard_blocked_item(item):
                    out.skipped_generation_count += 1
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
                        status=pres.status,
                        patch_content_available=available,
                        reason="" if available else (pres.warnings[0] if pres.warnings else ""),
                    )
                )
                if available:
                    out.generated_count += 1
            self._emit("autonomous_codegen_patch_generation_completed", request.pool_id, run_id, orchestrator_run_id, status="completed", generated_count=out.generated_count, skipped_count=out.skipped_generation_count)

        # ── Phase 3: multi-item apply (inherits full_auto relaxation + verify/self-correct) ───
        out.phase = "apply"
        autopilot = self.multi_item_autopilot_service.run(
            AtlasMultiItemAutopilotRequest(
                pool_id=request.pool_id,
                run_id=run_id,
                workspace_id=request.workspace_id,
                project_path=request.project_path,
                item_ids=request.item_ids,
                policy_id=request.policy_id,
                require_approval=False,
                max_items=request.max_items,
                max_runtime_seconds=request.max_runtime_seconds,
                max_changed_files_total=request.max_changed_files_total,
                include_context_refresh=True,
                include_evaluator=True,
                include_bounded_retry=True,
                include_self_correction=True,
                include_correction_routing=True,
                include_harness_provisioning=True,
            )
        )
        out.autopilot_result = autopilot.model_dump()
        out.stop_reason = autopilot.stop_reason
        for w in autopilot.warnings:
            if w not in out.warnings:
                out.warnings.append(w)

        # ── Phase 4: aggregate ────────────────────────────────────────────────────────────────
        out.phase = "completed"
        out.status = autopilot.status or "completed"
        out.metadata.update(
            {
                "autopilot_run_id": autopilot.autopilot_run_id,
                "processed_count": autopilot.processed_count,
                "completed_count": autopilot.completed_count,
                "failed_count": autopilot.failed_count,
                "blocked_count": autopilot.blocked_count,
            }
        )
        self._emit("autonomous_codegen_completed", request.pool_id, run_id, orchestrator_run_id, status=out.status)
        return out

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
