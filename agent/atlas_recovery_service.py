from __future__ import annotations

from pathlib import Path

from agent.atlas_journal import AtlasJournal
from agent.atlas_journal_schema import AtlasRecoverySummary, AtlasRecoveryStatus
from agent.atlas_pipeline_runner_schema import AtlasPipelineRunState
from agent.atlas_plan_pool_schema import AtlasPlanPool


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
        return AtlasRecoverySummary(
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
            return AtlasRecoverySummary(
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
        events = self.journal.read_events(pool_id, run_id)
        last_event = events[-1] if events else {}
        status = self._status_from_state(state, bool(last_event))
        paths = self.journal.paths(pool_id=pool_id, run_id=run_id)
        return AtlasRecoverySummary(
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
            return "Review approval requirements and continue pipeline."
        if status == "failed":
            return "Inspect failure logs and prepare debug loop."
        if status == "completed":
            return "Review final report or start next plan pool."
        if status in {"no_workspace", "no_plan_pool", "no_pipeline_run"}:
            return "Create or select an Atlas plan pool."
        if status == "blocked":
            return "Inspect blocked items and resolve requirements before continuing."
        if status in {"stale", "interrupted"}:
            return "Start a new dry-run from the recovered PlanPool."
        return "Continue pipeline from the recovered checkpoint."
