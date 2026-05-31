from __future__ import annotations

from typing import Any

from agent.atlas_orchestration_summary_schema import AtlasOrchestrationSummary
from agent.atlas_pipeline_runner_schema import AtlasPipelineRunState
from agent.atlas_plan_pool_schema import AtlasPlanPool


def _summary_copy(summary: AtlasOrchestrationSummary, update: dict[str, Any]) -> AtlasOrchestrationSummary:
    if hasattr(summary, "model_copy"):
        return summary.model_copy(update=update)
    return summary.copy(update=update)


def _model_dump(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return dict(value)


class AtlasOrchestrationSummaryBuilder:
    def build_from_create_plan_response(self, response: dict) -> AtlasOrchestrationSummary:
        payload = _model_dump(response)
        pool = payload.get("plan_pool") or None
        status = str(payload.get("status") or "")
        if status == "waiting_for_clarification":
            summary = self._summary_for_status(
                status="waiting_for_clarification",
                pool_id="",
                run_id="",
                warnings=list(payload.get("warnings") or []),
                errors=list(payload.get("errors") or []),
                metadata={
                    "planner_mode": payload.get("planner_mode", ""),
                    "planner_status": payload.get("planner_status", ""),
                    "used_fallback": bool(payload.get("used_fallback", False)),
                    "fallback_reason": payload.get("fallback_reason", ""),
                    "questions": list(payload.get("questions") or []),
                    "question_count": len(list(payload.get("questions") or [])),
                },
            )
            return summary
        base_summary = self.build_from_pool_and_state(pool, None)
        return _summary_copy(base_summary, {
            "status": status or (pool or {}).get("status", ""),
            "warnings": list(payload.get("warnings") or []),
            "errors": list(payload.get("errors") or []),
            "metadata": {
                **base_summary.metadata,
                "planner_status": payload.get("planner_status", ""),
                "used_fallback": bool(payload.get("used_fallback", False)),
                "fallback_reason": payload.get("fallback_reason", ""),
                "question_count": len(list(payload.get("questions") or [])),
            },
        })

    def build_from_pool_and_state(
        self,
        pool: AtlasPlanPool | dict | None,
        state: AtlasPipelineRunState | dict | None,
        recovery: dict | None = None,
    ) -> AtlasOrchestrationSummary:
        pool_data = _model_dump(pool)
        state_data = _model_dump(state)
        recovery_data = _model_dump(recovery)
        pool_id = str(state_data.get("pool_id") or pool_data.get("pool_id") or recovery_data.get("pool_id") or "")
        run_id = str(state_data.get("run_id") or recovery_data.get("run_id") or "")
        status = str(
            recovery_data.get("status")
            or state_data.get("status")
            or pool_data.get("status")
            or ""
        )
        current_item_id = str(state_data.get("current_item_id") or pool_data.get("current_item_id") or recovery_data.get("current_item_id") or "")
        current_item_title = str(recovery_data.get("current_item_title") or self._item_title(pool_data, current_item_id) or "")
        warnings = [*list(pool_data.get("warnings") or []), *list(state_data.get("warnings") or []), *list(recovery_data.get("warnings") or [])]
        errors = [*list(pool_data.get("errors") or []), *list(state_data.get("errors") or []), *list(recovery_data.get("errors") or [])]
        _pool_meta = pool_data.get("metadata") or {}
        metadata = {
            "pool_status": pool_data.get("status", ""),
            "state_status": state_data.get("status", ""),
            "recovery_status": recovery_data.get("status", ""),
            "planner_status": _pool_meta.get("planner_status", ""),
            "used_fallback": bool(_pool_meta.get("used_fallback", False)),
            "fallback_reason": _pool_meta.get("fallback_reason", ""),
            # PR-9d: surface quality rollup and preference summary for UI/API consumers
            "quality_rollup": _pool_meta.get("quality_rollup") or {},
            "feature_summary": _pool_meta.get("feature_summary") or {},
            "plan_revision_required": bool(_pool_meta.get("plan_revision_required")),
            "critique_clarification_options": _pool_meta.get("critique_clarification_options") or {},
        }
        if self._has_approval_required(pool_data, state_data) and status not in {"failed", "blocked", "completed", "completed_with_warnings", "stale"}:
            status = "approval_required"
        if not pool_data and not state_data and not recovery_data:
            status = "no_pool"
        return self._summary_for_status(status, pool_id, run_id, current_item_id, current_item_title, warnings, errors, metadata)

    def build_from_recovery(self, recovery: Any) -> AtlasOrchestrationSummary:
        recovery_data = _model_dump(recovery)
        return self.build_from_pool_and_state(None, None, recovery=recovery_data)

    def _summary_for_status(
        self,
        status: str,
        pool_id: str = "",
        run_id: str = "",
        current_item_id: str = "",
        current_item_title: str = "",
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
        metadata: dict | None = None,
    ) -> AtlasOrchestrationSummary:
        s = str(status or "").lower()
        warnings = list(dict.fromkeys(warnings or []))
        errors = list(dict.fromkeys(errors or []))
        metadata = dict(metadata or {})
        base = AtlasOrchestrationSummary(
            pool_id=pool_id,
            run_id=run_id,
            status=status if status != "no_pool" else "",
            current_item_id=current_item_id,
            current_item_title=current_item_title,
            warnings=warnings,
            errors=errors,
            metadata=metadata,
            can_load_plan=bool(pool_id),
            can_continue=bool(pool_id or run_id),
        )
        if s in {"", "no_pool", "no_workspace", "no_plan_pool", "no_pipeline_run"}:
            return _summary_copy(base, {"phase": "not_started", "next_action": "Create a PlanPool to begin.", "user_message": "No PlanPool is selected yet."})
        if s == "waiting_for_clarification":
            return _summary_copy(base, {"phase": "clarification_required", "severity": "warning", "requires_clarification": True, "next_action": "Review planner questions in Details and refine the goal.", "user_message": "Additional planner clarification is required before creating a PlanPool."})
        if s in {"approval_required"}:
            return _summary_copy(base, {"phase": "approval_required", "severity": "warning", "requires_approval": True, "next_action": "Open Details / Advanced Panel → Approval Gate.", "user_message": "The pipeline is paused at an approval gate."})
        if s in {"paused", "waiting", "dependency_waiting"}:
            return _summary_copy(base, {"phase": "dependency_waiting", "severity": "warning", "next_action": "Resolve dependencies or regenerate PlanPool.", "user_message": "No ready item remains. Check dependencies or approve required items."})
        if s in {"stale", "interrupted"}:
            return _summary_copy(base, {"phase": "stale_recovery", "severity": "warning", "is_stale": True, "can_start_dry_run": bool(pool_id), "next_action": "Start a new dry-run from the recovered PlanPool.", "user_message": "Recovered PlanPool is available, but the previous run state is stale."})
        if s == "running" or (s == "created" and run_id):
            return _summary_copy(base, {"phase": "running", "can_refresh_status": True, "next_action": "Refresh status to update pipeline progress.", "user_message": "Atlas pipeline is in progress."})
        if s in {"completed", "completed_with_warnings"}:
            return _summary_copy(base, {"phase": "completed", "severity": "success", "is_terminal": True, "next_action": "Review the result or create the next PlanPool.", "user_message": "Atlas pipeline completed."})
        if s == "failed":
            return _summary_copy(base, {"phase": "failed", "severity": "danger", "is_terminal": True, "next_action": "Inspect failed items and prepare a debug follow-up.", "user_message": "Atlas pipeline failed. No debug runner is started automatically."})
        if s == "blocked":
            return _summary_copy(base, {"phase": "blocked", "severity": "danger", "next_action": "Review blocked items and policy/approval reasons.", "user_message": "Atlas pipeline is blocked by policy or approval requirements."})
        if pool_id and not run_id and s in {"ready", "draft", "approved"}:
            return _summary_copy(base, {"phase": "plan_ready", "can_start_dry_run": True, "next_action": "Start Dry-run to validate the PlanPool.", "user_message": "PlanPool is ready for dry-run validation."})
        return _summary_copy(base, {"phase": "plan_ready" if pool_id and not run_id else "running", "can_start_dry_run": bool(pool_id and not run_id), "can_refresh_status": bool(run_id), "next_action": "Start Dry-run to validate the PlanPool." if pool_id and not run_id else "Refresh status to update pipeline progress."})

    @staticmethod
    def _item_title(pool_data: dict[str, Any], item_id: str) -> str:
        for item in pool_data.get("items") or []:
            if item.get("item_id") == item_id:
                return str(item.get("title") or "")
        return ""

    @staticmethod
    def _has_approval_required(pool_data: dict[str, Any], state_data: dict[str, Any]) -> bool:
        if pool_data.get("status") == "approval_required":
            return True
        for item in pool_data.get("items") or []:
            if item.get("status") == "approval_required" or item.get("requires_user_confirmation"):
                return True
        for result in state_data.get("item_results") or []:
            if result.get("status") == "approval_required":
                return True
        return False
