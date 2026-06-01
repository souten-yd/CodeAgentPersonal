from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from uuid import uuid4

from app.atlas.candidate_workspace_manager import load_candidate_workspace_plan
from agent.atlas_autonomous_codegen_orchestrator_schema import (
    AtlasAutonomousCodegenProposalResult,
    AtlasAutonomousCodegenRequest,
    AtlasAutonomousCodegenResult,
)
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

    def __init__(self, *, storage, journal, patch_proposal_service, multi_item_autopilot_service, data_root=None):
        self.storage = storage
        self.journal = journal
        self.patch_proposal_service = patch_proposal_service
        self.multi_item_autopilot_service = multi_item_autopilot_service
        self.data_root = Path(data_root or getattr(journal, "root_dir", "ca_data"))

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
        out.metadata["phase_order"] = list(_AUTONOMOUS_PHASES)
        self._emit("autonomous_codegen_started", request.pool_id, run_id, orchestrator_run_id, status="started")

        # ── Phase 0: load + tag the pool as full_autopilot ───────────────────────────────────
        out.phase = "understanding_goal"
        pool = self.storage.load_pool(request.pool_id)
        preflight = self._preflight(request, pool)
        out.metadata["preflight"] = preflight
        out.metadata["workspace_evidence"] = preflight.get("workspace_evidence", {})
        out.metadata["recovery_evidence"] = preflight.get("recovery_evidence", {})
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
        out.phase = "candidate_apply"
        autopilot = self.multi_item_autopilot_service.run(
            AtlasMultiItemAutopilotRequest(
                pool_id=request.pool_id,
                run_id=run_id,
                workspace_id=request.workspace_id,
                project_path=str(preflight.get("effective_project_path") or request.project_path),
                item_ids=request.item_ids,
                policy_id=request.policy_id,
                require_approval=False,
                max_items=min(request.max_items, request.max_actions),
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
        out.phase = "final_summary"
        out.status = autopilot.status or "completed"
        out.metadata.update(
            {
                "autopilot_run_id": autopilot.autopilot_run_id,
                "processed_count": autopilot.processed_count,
                "completed_count": autopilot.completed_count,
                "failed_count": autopilot.failed_count,
                "blocked_count": autopilot.blocked_count,
                "changed_files": self._changed_files_from_autopilot(autopilot),
                "draft_pr_readiness": {
                    "ready": out.status in {"completed", "partial"},
                    "direct_merge_enabled": False,
                    "remote_git_push_enabled": False,
                    "self_apply_enabled": False,
                    "stable_runtime_mutation_enabled": False,
                },
            }
        )
        self._emit("autonomous_codegen_completed", request.pool_id, run_id, orchestrator_run_id, status=out.status)
        self.save_result(out)
        return out

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
        blocked = [p for p in paths if self._matches_prefix(p, request.blocked_paths or list(((envelope.get("bounds") or {}).get("blocked_paths") or [])))]
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
        allowed = request.allowed_paths or list(((envelope.get("bounds") or {}).get("allowed_paths") or []))
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
        return {
            "status": "ok",
            "normalized_profile": profile,
            "project_path": project_path,
            "effective_project_path": workspace_evidence.get("effective_project_path") or project_path,
            "paths": paths,
            "envelope_id": envelope_id,
            "warnings": warnings,
            "workspace_evidence": workspace_evidence,
            "recovery_evidence": recovery_evidence,
        }

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
        return {
            "work_target": work_target,
            "project_path": project_path,
            "effective_project_path": effective_project_path,
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
        return {
            "references": refs,
            "summary": summary,
            "restore_executed": False,
            "rollback_executed": False,
            "recovery_execution_performed": False,
            "warnings": sorted(set(warnings)),
        }

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
        return any(str(path).startswith(str(prefix).replace("\\", "/")) for prefix in prefixes or [])

    @staticmethod
    def _changed_files_from_autopilot(autopilot) -> list[str]:
        changed: list[str] = []
        for item in getattr(autopilot, "item_results", []) or []:
            for path in getattr(item, "changed_files", []) or []:
                if path not in changed:
                    changed.append(path)
        return changed

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
