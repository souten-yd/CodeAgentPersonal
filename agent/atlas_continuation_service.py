from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.atlas_continuation_schema import AtlasContinuationSummary
from agent.atlas_journal import AtlasJournal
from agent.atlas_recovery_service import AtlasRecoveryService


def _model_dump(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return dict(value)


class AtlasContinuationService:
    def __init__(self, journal: AtlasJournal):
        self.journal = journal
        self.recovery = AtlasRecoveryService(journal)

    def build_latest_summary(self) -> AtlasContinuationSummary:
        recovery = self.recovery.recover_latest()
        summary = self._summary_from_recovery(_model_dump(recovery))
        return self._finalize(summary)

    def build_pool_summary(self, pool_id: str, run_id: str = "") -> AtlasContinuationSummary:
        if run_id:
            recovery = self.recovery.recover_run(pool_id, run_id)
        else:
            recovery = self.recovery.recover_pool(pool_id)
        summary = self._summary_from_recovery(_model_dump(recovery))
        return self._finalize(summary)

    def build_prompt(self, summary: AtlasContinuationSummary) -> str:
        return f"""CodeAgentPersonal / KasaneCore のAtlas統合改修の続きです。

現在の状態:
- Workspace: {summary.workspace_id}
- Pool ID: {summary.pool_id}
- Run ID: {summary.run_id}
- Status: {summary.status}
- Current Goal: {summary.current_goal}
- Current Item: {summary.current_item_id} / {summary.current_item_title}
- Progress: {summary.completed_count}/{summary.total_items} completed, failed={summary.failed_count}, blocked={summary.blocked_count}
- Last Event: {summary.last_event_type} - {summary.last_event_message}
- Next Action: {summary.next_action}

重要方針:
- Task独立機能は廃止。
- Task = PlanItem。
- Agent独立機能は廃止。
- Agent = Autopilot。
- PlannerはPlanPoolを作る。
- AutopilotはPlanPoolをpipeline実行する。
- Journal / Markdown / events.ndjson を正として状態復元する。
- safe_apply / TestCommand / DebugLoop / DeepResearchの自動実行はまだしない。
- 現在のCreate Planはfallback PlanPoolを生成する。実Planner統合は次段階。

次にやること:
{summary.next_action}

必要に応じて、以下のファイルを確認:
- Checkpoint: {summary.checkpoint_md_path}
- PlanPool Markdown: {summary.plan_pool_md_path}
- Pipeline State: {summary.state_json_path}
- Events: {summary.events_ndjson_path}

この状態から、実装状況を確認して次の指示を出してください。"""

    def read_checkpoint_excerpt(self, pool_id: str = "", max_chars: int = 4000) -> str:
        paths = self.journal.paths(pool_id=pool_id) if pool_id else self.journal.paths()
        path = Path(paths.checkpoint_md)
        if not path.exists():
            return ""
        text = path.read_text(encoding="utf-8")
        limit = max(0, int(max_chars))
        return text[:limit]

    def _summary_from_recovery(self, recovery: dict[str, Any]) -> AtlasContinuationSummary:
        pool_id = str(recovery.get("pool_id") or "")
        run_id = str(recovery.get("run_id") or "")
        paths = self.journal.paths(pool_id=pool_id, run_id=run_id) if pool_id else self.journal.paths()
        summary = AtlasContinuationSummary(
            workspace_id=str(recovery.get("workspace_id") or self.journal.workspace_id),
            pool_id=pool_id,
            run_id=run_id,
            status=str(recovery.get("status") or ""),
            current_item_id=str(recovery.get("current_item_id") or ""),
            current_item_title=str(recovery.get("current_item_title") or ""),
            completed_count=int(recovery.get("completed_count") or 0),
            failed_count=int(recovery.get("failed_count") or 0),
            blocked_count=int(recovery.get("blocked_count") or 0),
            total_items=int(recovery.get("total_items") or 0),
            last_event_type=str(recovery.get("last_event_type") or ""),
            last_event_message=str(recovery.get("last_event_message") or ""),
            next_action=str(recovery.get("next_action") or ""),
            checkpoint_md_path=str(recovery.get("checkpoint_md_path") or paths.checkpoint_md),
            plan_pool_md_path=str(paths.plan_pool_md),
            state_json_path=str(recovery.get("state_json_path") or paths.pipeline_state_json),
            events_ndjson_path=str(recovery.get("events_ndjson_path") or paths.events_ndjson),
            warnings=list(recovery.get("warnings") or []),
            errors=list(recovery.get("errors") or []),
            metadata={"recovery": dict(recovery.get("metadata") or {})},
        )
        return summary

    def _finalize(self, summary: AtlasContinuationSummary) -> AtlasContinuationSummary:
        pool = None
        if summary.pool_id:
            try:
                pool = self.journal.load_plan_pool(summary.pool_id)
            except FileNotFoundError:
                summary.warnings.append("plan_pool_not_found")
            if pool is not None:
                summary.current_goal = pool.root_goal
                if not summary.current_item_id:
                    summary.current_item_id = pool.current_item_id
                if not summary.current_item_title and summary.current_item_id:
                    item = pool.get_item(summary.current_item_id)
                    summary.current_item_title = item.title if item else ""
                if not summary.total_items:
                    summary.total_items = len(pool.items)
                if summary.completed_count == 0:
                    summary.completed_count = len(pool.completed_item_ids)
                if summary.failed_count == 0:
                    summary.failed_count = len(pool.failed_item_ids)
                if summary.blocked_count == 0:
                    summary.blocked_count = len(pool.blocked_item_ids)
        if summary.pool_id and summary.run_id:
            try:
                state = self.journal.load_pipeline_state(summary.pool_id, summary.run_id)
            except FileNotFoundError:
                state = None
            if state is not None:
                summary.status = state.status or summary.status
                summary.current_item_id = state.current_item_id or summary.current_item_id
                summary.completed_count = len(state.completed_item_ids)
                summary.failed_count = len(state.failed_item_ids)
                summary.blocked_count = len(state.blocked_item_ids)
                events = self.journal.read_events(summary.pool_id, summary.run_id)
                last_event = events[-1] if events else (_model_dump(state.events[-1]) if state.events else {})
                summary.last_event_type = str(last_event.get("event_type") or summary.last_event_type)
                summary.last_event_message = str(last_event.get("message") or summary.last_event_message)
                if pool is not None and summary.current_item_id:
                    item = pool.get_item(summary.current_item_id)
                    summary.current_item_title = item.title if item else summary.current_item_title
        summary.metadata["checkpoint_excerpt"] = self.read_checkpoint_excerpt(summary.pool_id, max_chars=4000)
        summary.continuation_prompt = self.build_prompt(summary)
        return summary
