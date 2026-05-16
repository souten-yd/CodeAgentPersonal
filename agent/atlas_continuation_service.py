from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.atlas_continuation_schema import AtlasContinuationSummary
from agent.atlas_journal import AtlasJournal
from agent.atlas_orchestration_summary import AtlasOrchestrationSummaryBuilder
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

Planning:
- planner_mode: {summary.metadata.get("planner_mode", "")}
- planner_status: {summary.metadata.get("planner_status", "")}
- used_fallback: {str(bool(summary.metadata.get("used_fallback", False))).lower()}
- fallback_reason: {summary.metadata.get("fallback_reason", "")}
- questions_count: {summary.metadata.get("questions_count", 0)}
- clarification_session_id: {summary.metadata.get("clarification_session_id", "")}
- orchestration_next_action: {summary.metadata.get("orchestration_next_action", summary.next_action)}

Current Gate:
- gate: {summary.metadata.get("current_gate", "none")}
- requires_clarification: {str(bool(summary.metadata.get("requires_clarification", False))).lower()}
- requires_approval: {str(bool(summary.metadata.get("requires_approval", False))).lower()}
- stale_recovery_warning: {summary.metadata.get("stale_recovery_warning", "")}
- approval_pending_count: {summary.metadata.get("approval_pending_count", 0)}
- approval_approved_count: {summary.metadata.get("approval_approved_count", 0)}
- approval_rejected_count: {summary.metadata.get("approval_rejected_count", 0)}
- approval_pending_item_ids: {summary.metadata.get("approval_pending_item_ids", [])}
- approval_note: Approval records exist, but safe_apply is not automatically executed.
- debug_review_status: {summary.metadata.get("debug_review_status", "")}
- debug_review_root_cause_category: {summary.metadata.get("debug_review_root_cause_category", "")}
- debug_review_proposed_fix: {summary.metadata.get("debug_review_proposed_fix", "")}
- debug_review_retry_recommended: {str(bool(summary.metadata.get("debug_review_retry_recommended", False))).lower()}
- debug_review_advisory_only: {str(bool(summary.metadata.get("debug_review_advisory_only", False))).lower()}
- debug_review_note: no patch/safe_apply/reverification was run.
- patch_proposal_status: {summary.metadata.get("patch_proposal_status", "")}
- patch_proposal_summary: {summary.metadata.get("patch_proposal_summary", "")}
- patch_proposal_risk_level: {summary.metadata.get("patch_proposal_risk_level", "")}
- patch_proposal_md_path: {summary.metadata.get("patch_proposal_md_path", "")}
- patch_proposal_note: proposal only, no patch/safe_apply/reverification was run

重要方針:
- Task独立機能は廃止。
- Task = PlanItem。
- Agent独立機能は廃止。
- Agent = Autopilot。
- PlannerはPlanPoolを作る。
- AutopilotはPlanPoolをpipeline実行する。
- Journal / Markdown / events.ndjson を正として状態復元する。
- safe_apply / TestCommand / DebugLoop / DeepResearchの自動実行はまだしない。
- Create Planはplanner_modeに応じてreal Plannerまたはfallback PlanPoolを使う。fallback_usedの場合はreal Planner接続/LLM JSON functionを確認する。
- waiting_for_clarificationの場合、次チャットではPlanner questionsを確認してgoalを補足する。
- Questions are waiting in Atlas Dashboard Details
- Answer them or choose assumptions, then re-plan
- approval_requiredの場合、approval対象を確認し、自動実行は開始しない。
- staleの場合、recovered PlanPoolから新しいdry-runを開始する。

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
        state = None
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
        recovery_metadata = dict(summary.metadata.get("recovery") or {})
        orchestration = AtlasOrchestrationSummaryBuilder().build_from_pool_and_state(pool, state if summary.pool_id and summary.run_id else None, recovery=recovery_metadata)
        orchestration_data = _model_dump(orchestration)
        pool_metadata = _model_dump(pool).get("metadata", {}) if pool is not None else {}
        summary.metadata.update({
            "orchestration_summary": orchestration_data,
            "orchestration_next_action": orchestration.next_action,
            "planner_mode": pool_metadata.get("planner_mode", pool_metadata.get("mode", "")),
            "planner_status": pool_metadata.get("planner_status", ""),
            "used_fallback": bool(pool_metadata.get("used_fallback", False)),
            "fallback_reason": pool_metadata.get("fallback_reason", ""),
            "requires_clarification": orchestration.requires_clarification,
            "requires_approval": orchestration.requires_approval,
            "questions_count": int(pool_metadata.get("questions_count", 0) or pool_metadata.get("question_count", 0) or 0),
            "stale_recovery_warning": "Start a new dry-run from the recovered PlanPool." if orchestration.is_stale else "",
            "current_gate": self._current_gate(orchestration),
        })
        approval_pending_items = []
        approval_approved_count = 0
        approval_rejected_count = 0
        if pool is not None:
            for item in pool.items:
                decision = str((item.metadata or {}).get("approval", {}).get("decision", ""))
                if item.status in {"approval_required", "paused"}:
                    approval_pending_items.append(item.item_id)
                if decision == "approved":
                    approval_approved_count += 1
                if decision in {"rejected", "needs_revision"}:
                    approval_rejected_count += 1
        summary.metadata.update({
            "approval_pending_count": len(approval_pending_items),
            "approval_approved_count": approval_approved_count,
            "approval_rejected_count": approval_rejected_count,
            "approval_pending_item_ids": approval_pending_items,
        })
        if not summary.next_action or summary.next_action in {"Continue pipeline from the recovered checkpoint."}:
            summary.next_action = orchestration.next_action or summary.next_action
        debug_review = self._latest_debug_review(pool)
        if debug_review:
            summary.metadata.update({
                "debug_review_status": str(debug_review.get("status") or ""),
                "debug_review_root_cause_category": str(debug_review.get("root_cause_category") or ""),
                "debug_review_proposed_fix": str(debug_review.get("proposed_fix") or ""),
                "debug_review_retry_recommended": bool(debug_review.get("retry_recommended", False)),
                "debug_review_advisory_only": True,
            })
        patch_proposal = self._latest_patch_proposal(pool)
        if patch_proposal:
            summary.metadata.update({
                "patch_proposal_status": str(patch_proposal.get("status") or ""),
                "patch_proposal_summary": str(patch_proposal.get("summary") or ""),
                "patch_proposal_risk_level": str(patch_proposal.get("risk_level") or ""),
                "patch_proposal_md_path": str(patch_proposal.get("proposal_md_path") or ""),
            })
        summary.metadata["checkpoint_excerpt"] = self.read_checkpoint_excerpt(summary.pool_id, max_chars=4000)
        summary.continuation_prompt = self.build_prompt(summary)
        return summary


    def _latest_debug_review(self, pool) -> dict[str, Any]:
        latest: dict[str, Any] = {}
        if pool is None:
            return latest
        for item in pool.items:
            debug = dict((item.metadata or {}).get("debug_review") or {})
            if not debug:
                continue
            reviewed_at = str(debug.get("reviewed_at") or "")
            if not latest or reviewed_at >= str(latest.get("reviewed_at") or ""):
                latest = dict(debug)
        return latest

    def _latest_patch_proposal(self, pool) -> dict[str, Any]:
        latest: dict[str, Any] = {}
        if pool is None:
            return latest
        for item in pool.items:
            proposal = dict((item.metadata or {}).get("patch_proposal") or {})
            if not proposal:
                continue
            proposed_at = str(proposal.get("proposed_at") or "")
            if not latest or proposed_at >= str(latest.get("proposed_at") or ""):
                latest = dict(proposal)
        return latest

    @staticmethod
    def _current_gate(orchestration) -> str:
        if orchestration.requires_clarification:
            return "clarification_required"
        if orchestration.requires_approval:
            return "approval_required"
        if orchestration.is_stale:
            return "stale"
        return "none"
