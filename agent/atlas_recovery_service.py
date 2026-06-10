from __future__ import annotations

from pathlib import Path

from agent.atlas_journal import AtlasJournal
from agent.atlas_journal_schema import AtlasRecoverySummary, AtlasRecoveryStatus
from agent.atlas_pipeline_runner_schema import AtlasPipelineRunState
from agent.atlas_plan_pool_schema import AtlasPlanPool
from agent.project_twin.project_identity import compute_working_tree_hash


class AtlasRecoveryService:
    def __init__(self, journal: AtlasJournal):
        self.journal = journal

    def recover_latest(self) -> AtlasRecoverySummary:
        if not self.journal.workspace_dir().exists():
            return self._empty_summary("no_workspace")
        pool_id = self.journal.latest_pool_id()
        if not pool_id:
            return self._empty_summary("no_plan_pool")
        run_id = self.journal.latest_run_id(pool_id)
        if not run_id:
            return self.recover_pool(pool_id)
        return self.recover_run(pool_id, run_id)

    def recover_pool(self, pool_id: str) -> AtlasRecoverySummary:
        if not self.journal.workspace_dir().exists():
            return self._empty_summary("no_workspace", pool_id=pool_id)
        plan_pools_dir = self.journal.workspace_dir() / "plan_pools"
        if not plan_pools_dir.exists():
            return self._empty_summary("no_plan_pool", pool_id=pool_id)
        try:
            pool = self.journal.load_plan_pool(pool_id)
        except FileNotFoundError:
            return self._empty_summary("no_plan_pool", pool_id=pool_id)
        run_id = self.journal.latest_run_id(pool_id)
        if run_id:
            return self.recover_run(pool_id, run_id)
        paths = self.journal.paths(pool_id=pool_id)
        summary = AtlasRecoverySummary(
            workspace_id=self.journal.workspace_id,
            pool_id=pool_id,
            status=self._status_from_pool(pool),
            current_item_id=pool.current_item_id,
            current_item_title=self._item_title(pool, pool.current_item_id),
            completed_count=len(pool.completed_item_ids),
            failed_count=len(pool.failed_item_ids),
            blocked_count=len(pool.blocked_item_ids),
            total_items=len(pool.items),
            next_action=self._next_action(self._status_from_pool(pool)),
            checkpoint_md_path=paths.checkpoint_md,
            warnings=list(pool.warnings),
            errors=list(pool.errors),
            metadata={"source": "plan_pool"},
        )
        return self._apply_project_intelligence_recovery(summary, pool)

    def recover_run(self, pool_id: str, run_id: str) -> AtlasRecoverySummary:
        if not self.journal.workspace_dir().exists():
            return self._empty_summary("no_workspace", pool_id=pool_id, run_id=run_id)
        try:
            pool = self.journal.load_plan_pool(pool_id)
        except FileNotFoundError:
            pool = None
        try:
            state = self.journal.load_pipeline_state(pool_id, run_id)
        except FileNotFoundError:
            if pool is None:
                return self._empty_summary("no_pipeline_run", pool_id=pool_id, run_id=run_id)
            paths = self.journal.paths(pool_id=pool_id, run_id=run_id)
            summary = AtlasRecoverySummary(
                workspace_id=self.journal.workspace_id,
                pool_id=pool_id,
                run_id=run_id,
                status="stale",
                current_item_id=pool.current_item_id,
                current_item_title=self._item_title(pool, pool.current_item_id),
                completed_count=len(pool.completed_item_ids),
                failed_count=len(pool.failed_item_ids),
                blocked_count=len(pool.blocked_item_ids),
                total_items=len(pool.items),
                next_action="Start a new dry-run from the recovered PlanPool.",
                checkpoint_md_path=paths.checkpoint_md,
                state_json_path=paths.pipeline_state_json,
                events_ndjson_path=paths.events_ndjson,
                warnings=["pipeline_state_not_found", *list(pool.warnings)],
                errors=list(pool.errors),
                metadata={"source": "plan_pool", "stale_run_id": run_id},
            )
            return self._apply_project_intelligence_recovery(summary, pool)
        events = self.journal.read_events(pool_id, run_id)
        last_event = events[-1] if events else {}
        status = self._status_from_state(state, bool(last_event))
        paths = self.journal.paths(pool_id=pool_id, run_id=run_id)
        summary = AtlasRecoverySummary(
            workspace_id=self.journal.workspace_id,
            pool_id=pool_id,
            run_id=run_id,
            status=status,
            current_item_id=state.current_item_id,
            current_item_title=self._item_title(pool, state.current_item_id) if pool else "",
            completed_count=len(state.completed_item_ids),
            failed_count=len(state.failed_item_ids),
            blocked_count=len(state.blocked_item_ids),
            total_items=len(pool.items) if pool else len(state.item_results),
            last_event_type=str(last_event.get("event_type", "")),
            last_event_message=str(last_event.get("message", "")),
            next_action=self._next_action(status),
            checkpoint_md_path=paths.checkpoint_md,
            state_json_path=paths.pipeline_state_json,
            events_ndjson_path=paths.events_ndjson,
            warnings=list(state.warnings) + (list(pool.warnings) if pool else []),
            errors=list(state.errors) + (list(pool.errors) if pool else []),
            metadata={"source": "pipeline_run", "has_event_log": bool(events)},
        )
        return self._apply_project_intelligence_recovery(summary, pool)

    def _empty_summary(
        self,
        status: AtlasRecoveryStatus,
        pool_id: str = "",
        run_id: str = "",
    ) -> AtlasRecoverySummary:
        paths = self.journal.paths(pool_id=pool_id, run_id=run_id) if pool_id else self.journal.paths()
        return AtlasRecoverySummary(
            workspace_id=self.journal.workspace_id,
            pool_id=pool_id,
            run_id=run_id,
            status=status,
            next_action=self._next_action(status),
            checkpoint_md_path=paths.checkpoint_md,
            state_json_path=paths.pipeline_state_json,
            events_ndjson_path=paths.events_ndjson,
        )

    @staticmethod
    def _status_from_pool(pool: AtlasPlanPool) -> AtlasRecoveryStatus:
        if pool.status in {"running", "paused", "completed", "failed", "blocked"}:
            return pool.status
        if pool.status == "completed_with_warnings":
            return "completed"
        return "ready"

    @staticmethod
    def _status_from_state(state: AtlasPipelineRunState, has_event_log: bool) -> AtlasRecoveryStatus:
        if state.status in {"paused", "completed", "failed", "blocked", "running"}:
            return state.status
        if state.status == "completed_with_warnings":
            return "completed"
        if state.status == "created" and has_event_log:
            return "running"
        return "ready"

    @staticmethod
    def _item_title(pool: AtlasPlanPool | None, item_id: str) -> str:
        if pool is None or not item_id:
            return ""
        item = pool.get_item(item_id)
        return item.title if item else ""

    @staticmethod
    def _next_action(status: AtlasRecoveryStatus) -> str:
        if status == "paused":
            return "Review approval-required items before continuing."
        if status == "failed":
            return "Inspect failed items and prepare a debug follow-up (debug loop planning only)."
        if status == "completed":
            return "Review final report or create the next PlanPool / next plan pool."
        if status in {"no_workspace", "no_plan_pool", "no_pipeline_run"}:
            return "Create or select an Atlas plan pool."
        if status == "blocked":
            return "Review blocked items and policy reasons."
        if status in {"stale", "interrupted"}:
            return "Start a new dry-run from the recovered PlanPool."
        if status == "ready":
            return "Start Dry-run to validate the generated PlanPool."
        return "Refresh status to update pipeline progress."

    def _apply_project_intelligence_recovery(
        self,
        summary: AtlasRecoverySummary,
        pool: AtlasPlanPool | None,
    ) -> AtlasRecoverySummary:
        if pool is None:
            return summary
        latest = self._latest_project_intelligence_verification(pool)
        final_gate = self._project_intelligence_final_gate(pool)
        if final_gate["enabled"]:
            summary.metadata["project_intelligence_final_gate"] = final_gate
        if latest:
            resume = self._project_intelligence_resume_metadata(pool, latest)
            summary.metadata["project_intelligence_checkpoint"] = resume
            for warning in resume.get("warnings") or []:
                if warning not in summary.warnings:
                    summary.warnings.append(warning)
            action = str(resume.get("resume_action") or "")
            if action == "refresh_needed":
                summary.status = "stale"
                summary.next_action = "Refresh Project Intelligence context and replan before continuing."
            elif action == "halt_unsafe":
                summary.status = "blocked"
                summary.next_action = "Halt without mutation and review the unsafe Project Intelligence decision."
            elif action == "request_critical_decision":
                summary.status = "blocked"
                summary.next_action = "Surface the critical decision through the existing approval gate before continuing."
            elif action == "repair_current_item":
                summary.next_action = "Run bounded repair/retry for the current item before downstream continuation."
            elif action == "replan_downstream":
                summary.next_action = "Replan downstream items while preserving completed PlanPool items."
            elif action == "revise_blueprint":
                summary.next_action = "Revise the Blueprint before continuing execution."
            elif action == "resume":
                summary.next_action = "Resume from the Project Intelligence checkpoint without duplicate apply or verification."
        if pool.status == "completed" and final_gate["enabled"] and not final_gate["passed"]:
            summary.status = "blocked"
            summary.next_action = "Resolve Project Intelligence final completion gate before marking completion."
            if "project_intelligence_final_gate_blocked" not in summary.warnings:
                summary.warnings.append("project_intelligence_final_gate_blocked")
        return summary

    @staticmethod
    def _latest_project_intelligence_verification(pool: AtlasPlanPool) -> dict:
        latest: dict = {}
        latest_at = ""
        for item in pool.items:
            verification = dict((item.metadata or {}).get("verification") or {})
            pi = dict(verification.get("project_intelligence_verification") or {})
            if not pi:
                continue
            verified_at = str(verification.get("verified_at") or "")
            if not latest or verified_at >= latest_at:
                latest = {**pi, "item_id": item.item_id, "verification_status": verification.get("status", "")}
                latest_at = verified_at
        return latest

    def _project_intelligence_resume_metadata(self, pool: AtlasPlanPool, latest: dict) -> dict:
        revisions = dict(latest.get("revisions") or {})
        expected_hash = str(revisions.get("working_tree_hash") or "")
        current_hash = ""
        project_path = str(pool.project_path or "")
        if project_path:
            try:
                root = Path(project_path)
                if root.is_dir():
                    current_hash = compute_working_tree_hash(root)
            except Exception:
                current_hash = ""
        route = dict(latest.get("decision_route") or {})
        action = str(route.get("action") or "resume")
        warnings: list[str] = []
        resume_action = action if action in {"repair_current_item", "replan_downstream", "revise_blueprint", "request_critical_decision", "halt_unsafe"} else "resume"
        blind_resume_allowed = resume_action == "resume"
        if expected_hash and current_hash and expected_hash != current_hash:
            resume_action = "refresh_needed"
            blind_resume_allowed = False
            warnings.append("project_intelligence_external_source_change")
        if str(latest.get("status") or "") != "recorded":
            resume_action = "refresh_needed"
            blind_resume_allowed = False
            warnings.append("project_intelligence_checkpoint_unavailable")
        return {
            "checkpoint_id": latest.get("checkpoint_id"),
            "item_id": latest.get("item_id"),
            "resume_action": resume_action,
            "blind_resume_allowed": blind_resume_allowed,
            "expected_working_tree_hash": expected_hash,
            "current_working_tree_hash": current_hash,
            "rollback_base_revision": latest.get("rollback_base_revision"),
            "decision_route": route,
            "convergence_decision": latest.get("convergence_decision") or {},
            "revisions": revisions,
            "warnings": warnings,
        }

    @staticmethod
    def _project_intelligence_final_gate(pool: AtlasPlanPool) -> dict:
        pi_items: list[str] = []
        blocked_reasons: list[str] = []
        for item in pool.items:
            verification = dict((item.metadata or {}).get("verification") or {})
            pi = dict(verification.get("project_intelligence_verification") or {})
            if not pi:
                continue
            pi_items.append(item.item_id)
            if str(verification.get("status") or "") != "passed":
                blocked_reasons.append(f"{item.item_id}:canonical_verification_not_passed")
            if pi.get("accepted") is not True:
                blocked_reasons.append(f"{item.item_id}:project_intelligence_not_accepted")
            route_action = str((pi.get("decision_route") or {}).get("action") or "")
            if route_action not in {"continue", "complete"}:
                blocked_reasons.append(f"{item.item_id}:decision_route_{route_action or 'unknown'}")
        enabled = bool(pi_items)
        return {
            "enabled": enabled,
            "passed": enabled and not blocked_reasons,
            "checked_item_ids": pi_items,
            "blocked_reasons": blocked_reasons,
            "requires_canonical_verification": True,
            "requires_project_intelligence_acceptance": True,
        }
