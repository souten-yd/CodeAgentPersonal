from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from agent.atlas_auto_policy_presets import DEFAULT_AUTO_POLICY_PRESET_ID
from agent.atlas_run_schema import AtlasRunState, TERMINAL_RUN_STATUSES
from agent.atlas_run_selection import RESUME_RETRYABLE_STATUSES, select_run_items
from agent.atlas_run_store import AtlasRunStore
from agent.atlas_time_utils import utc_now_iso


RunCallback = Callable[..., Any]


@dataclass
class AtlasRunOrchestratorRequest:
    run_id: str
    pool_id: str
    workspace_id: str = "default"
    item_id: str = ""
    item_ids: list[str] = field(default_factory=list)
    mode: str = "fresh"
    preset_id: str = DEFAULT_AUTO_POLICY_PRESET_ID
    command_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AtlasRunOrchestratorCallbacks:
    approve_plan_item: RunCallback
    generate_patch_proposal: RunCallback
    approve_patch_proposal: RunCallback
    apply_and_verify: RunCallback


class AtlasRunOrchestrator:
    def __init__(self, *, run_store: AtlasRunStore, plan_storage: Any, journal: Any, callbacks: AtlasRunOrchestratorCallbacks):
        self.run_store = run_store
        self.plan_storage = plan_storage
        self.journal = journal
        self.callbacks = callbacks

    def run_one_item(self, request: AtlasRunOrchestratorRequest) -> AtlasRunState:
        return self._run_one_item(request, complete_run=True)

    def run_items(self, request: AtlasRunOrchestratorRequest) -> AtlasRunState:
        state = self.run_store.load_state(request.run_id)
        if state.status in TERMINAL_RUN_STATUSES:
            self._event(state, "run_start_ignored", message="Run is already terminal.")
            return state
        if request.mode == "rerun":
            state = self.run_store.patch_state(
                state.run_id,
                {
                    "status": "running",
                    "phase": "planning",
                    "current_item_id": "",
                    "current_item_index": 0,
                    "completed_item_ids": [],
                    "failed_item_ids": [],
                    "blocked_item_ids": [],
                    "skipped_item_ids": [],
                    "requires_user_action": False,
                    "block_reason": "",
                    "error": "",
                    "next_actions": [],
                },
            )
            self._event(state, "run_rerun_reset", message="Run execution state reset for rerun.")
        pool = self.plan_storage.load_pool(request.pool_id)
        if request.item_ids:
            item_ids = list(request.item_ids)
            selection_source = "client_explicit_item_ids"
        else:
            item_ids = select_run_items(pool, state, request.mode, requested_item_id=request.item_id)
            selection_source = "backend_selection"
        state = self.run_store.patch_state(state.run_id, {"total_items": len(item_ids), "status": "running", "phase": "planning"})
        self._event(
            state,
            "run_items_selected",
            metadata={
                "item_ids": item_ids,
                "mode": request.mode,
                "selection_source": selection_source,
                "requested_item_id": request.item_id,
            },
        )
        if not item_ids:
            return self._complete_or_block_empty_selection(state, pool, request)
        self._event(state, "run_multi_item_started", metadata={"item_ids": item_ids, "mode": request.mode})
        for item_id in item_ids:
            state = self.run_store.load_state(request.run_id)
            if state.status == "cancelled":
                self._event(state, "run_cancel_observed", item_id=item_id, message="Cancellation observed between items.")
                return state
            if request.mode != "rerun" and item_id in set(state.completed_item_ids):
                skipped = list(dict.fromkeys([*state.skipped_item_ids, item_id]))
                state = self.run_store.patch_state(state.run_id, {"skipped_item_ids": skipped})
                self._event(state, "run_item_skipped_completed", item_id=item_id)
                continue
            item_request = AtlasRunOrchestratorRequest(
                run_id=request.run_id,
                pool_id=request.pool_id,
                workspace_id=request.workspace_id,
                item_id=item_id,
                item_ids=[],
                mode=request.mode,
                preset_id=request.preset_id,
                command_id=request.command_id,
                metadata=dict(request.metadata or {}),
            )
            state = self._run_one_item(item_request, complete_run=False)
            if state.status in {"failed", "blocked", "cancelled"}:
                return state
        final_state = self.run_store.load_state(request.run_id)
        completed = self.run_store.patch_state(
            final_state.run_id,
            {
                "status": "completed",
                "phase": "final_summary",
                "requires_user_action": False,
                "next_actions": [],
            },
        )
        self._event(completed, "run_completed", message="Multi-item backend run completed.")
        return completed

    def _complete_or_block_empty_selection(self, state: AtlasRunState, pool: Any, request: AtlasRunOrchestratorRequest) -> AtlasRunState:
        pool_completed = {str(item_id) for item_id in getattr(pool, "completed_item_ids", []) or [] if str(item_id)}
        completed = {str(item_id) for item_id in state.completed_item_ids or [] if str(item_id)}
        all_items = [str(getattr(item, "item_id", "") or "") for item in getattr(pool, "items", []) or []]
        all_item_ids = {item_id for item_id in all_items if item_id}
        if request.mode == "resume" and all_item_ids and all_item_ids.issubset(completed | pool_completed):
            done = self.run_store.patch_state(
                state.run_id,
                {
                    "status": "completed",
                    "phase": "final_summary",
                    "requires_user_action": False,
                    "next_actions": [],
                },
            )
            self._event(done, "run_completed", message="No remaining runnable items for resume.")
            return done
        blocked = self.run_store.patch_state(
            state.run_id,
            {
                "status": "blocked",
                "phase": "planning",
                "requires_user_action": True,
                "block_reason": "no_runnable_items",
                "next_actions": ["review_run_events", "revise_or_cancel"],
            },
        )
        self._event(blocked, "run_blocked", message="No runnable PlanItems were selected.")
        return blocked

    def _run_one_item(self, request: AtlasRunOrchestratorRequest, *, complete_run: bool) -> AtlasRunState:
        state = self.run_store.load_state(request.run_id)
        if state.status in TERMINAL_RUN_STATUSES:
            self._event(state, "run_start_ignored", message="Run is already terminal.")
            return state
        try:
            state = self._patch(
                state,
                {
                    "status": "running",
                    "phase": "planning",
                    "requires_user_action": False,
                    "error": "",
                    "block_reason": "",
                },
                event_type="run_started",
                message="Backend run orchestration started.",
            )
            pool = self.plan_storage.load_pool(request.pool_id)
            item = self._select_item(pool, request.item_id)
            state = self._patch(
                state,
                {
                    "current_item_id": item.item_id,
                    "current_item_index": self._item_index(pool, item.item_id),
                    "total_items": len(getattr(pool, "items", []) or []),
                },
                event_type="run_item_selected",
                item_id=item.item_id,
                message="Backend selected one PlanItem for execution.",
            )
            blocker = self._blocker(pool, item, mode=request.mode)
            if blocker:
                return self._block(state, item.item_id, blocker)

            approval = self.callbacks.approve_plan_item(pool=pool, item=item, request=request)
            self._event(state, "plan_item_approved", item_id=item.item_id, metadata=self._dump(approval))

            state = self._patch(state, {"phase": "proposal"}, event_type="patch_proposal_started", item_id=item.item_id)
            proposal = self.callbacks.generate_patch_proposal(pool=pool, item=item, request=request)
            proposal_payload = self._dump(proposal)
            proposal_status = str(proposal_payload.get("status") or "")
            if proposal_status not in {"proposed", "approved"} or proposal_payload.get("errors"):
                return self._fail_or_block(
                    state,
                    item.item_id,
                    proposal_payload,
                    default_event="patch_proposal_failed",
                    default_reason="patch_proposal_failed",
                )
            proposal_id = self._proposal_id(proposal_payload)
            self._event(
                state,
                "patch_proposal_completed",
                item_id=item.item_id,
                metadata={"status": proposal_status, "proposal_id": proposal_id},
            )

            approval_result = self.callbacks.approve_patch_proposal(
                pool=pool,
                item=item,
                request=request,
                proposal_id=proposal_id,
                proposal=proposal_payload,
            )
            approval_payload = self._dump(approval_result)
            if str(approval_payload.get("status") or "") != "approved" or approval_payload.get("errors"):
                return self._fail_or_block(
                    state,
                    item.item_id,
                    approval_payload,
                    default_event="patch_proposal_approval_failed",
                    default_reason="patch_proposal_approval_failed",
                )
            self._event(state, "patch_proposal_approved", item_id=item.item_id, metadata=approval_payload)

            state = self._patch(state, {"phase": "safe_apply"}, event_type="safe_apply_started", item_id=item.item_id)
            apply_verify = self.callbacks.apply_and_verify(pool=pool, item=item, request=request, proposal=proposal_payload)
            apply_payload = self._dump(apply_verify)
            apply_status = str(apply_payload.get("status") or "")
            if apply_status == "applied_and_verified":
                return self._complete(state, item.item_id, apply_payload, terminal=complete_run)
            if apply_status in {"safe_apply_blocked", "verification_blocked"}:
                return self._block(state, item.item_id, apply_status, metadata=apply_payload)
            return self._fail_or_block(
                state,
                item.item_id,
                apply_payload,
                default_event="safe_apply_or_verification_failed",
                default_reason=apply_status or "safe_apply_or_verification_failed",
            )
        except FileNotFoundError as exc:
            return self._mark_failed(request.run_id, "pool_not_found", exc)
        except Exception as exc:  # noqa: BLE001
            return self._mark_failed(request.run_id, "run_orchestrator_failed", exc)

    def _patch(
        self,
        state: AtlasRunState,
        patch: dict[str, Any],
        *,
        event_type: str,
        item_id: str = "",
        message: str = "",
    ) -> AtlasRunState:
        patch = {**dict(patch or {}), "worker_heartbeat_at": utc_now_iso()}
        next_state = self.run_store.patch_state(state.run_id, patch)
        self._event(next_state, event_type, item_id=item_id, message=message)
        return next_state

    def _event(
        self,
        state: AtlasRunState,
        event_type: str,
        *,
        item_id: str = "",
        message: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.run_store.append_event(
            state.run_id,
            event_type=event_type,
            phase=state.phase,
            status=state.status,
            item_id=item_id or state.current_item_id,
            message=message,
            metadata=dict(metadata or {}),
        )

    def _block(self, state: AtlasRunState, item_id: str, reason: str, *, metadata: dict[str, Any] | None = None) -> AtlasRunState:
        blocked = self.run_store.patch_state(
            state.run_id,
            {
                "status": "blocked",
                "phase": state.phase,
                "current_item_id": item_id,
                "blocked_item_ids": [item_id],
                "requires_user_action": True,
                "block_reason": reason,
                "next_actions": ["review_run_events", "revise_or_cancel"],
            },
        )
        self._event(blocked, "run_blocked", item_id=item_id, message=reason, metadata=dict(metadata or {}))
        return blocked

    def _complete(self, state: AtlasRunState, item_id: str, payload: dict[str, Any], *, terminal: bool) -> AtlasRunState:
        completed_ids = list(dict.fromkeys([*state.completed_item_ids, item_id]))
        if not terminal:
            item_completed = self.run_store.patch_state(
                state.run_id,
                {
                    "status": "running",
                    "phase": "planning",
                    "current_item_id": item_id,
                    "completed_item_ids": completed_ids,
                    "requires_user_action": False,
                    "metadata": {**dict(state.metadata or {}), "last_apply_verify_result": payload},
                },
            )
            self._event(item_completed, "run_item_completed", item_id=item_id, message="One item completed.", metadata=payload)
            return item_completed
        completed = self.run_store.patch_state(
            state.run_id,
            {
                "status": "completed",
                "phase": "final_summary",
                "current_item_id": item_id,
                "completed_item_ids": completed_ids,
                "requires_user_action": False,
                "next_actions": [],
                "metadata": {**dict(state.metadata or {}), "last_apply_verify_result": payload},
            },
        )
        self._event(completed, "run_completed", item_id=item_id, message="One-item backend run completed.", metadata=payload)
        return completed

    def _fail_or_block(self, state: AtlasRunState, item_id: str, payload: dict[str, Any], *, default_event: str, default_reason: str) -> AtlasRunState:
        warnings = [str(v) for v in payload.get("warnings") or []]
        errors = [str(v) for v in payload.get("errors") or []]
        status = str(payload.get("status") or "")
        reason = ";".join(errors or warnings or [default_reason])
        if status == "blocked" or warnings:
            return self._block(state, item_id, reason, metadata=payload)
        failed = self.run_store.patch_state(
            state.run_id,
            {
                "status": "failed",
                "phase": state.phase,
                "current_item_id": item_id,
                "failed_item_ids": [item_id],
                "error": reason,
                "requires_user_action": True,
                "next_actions": ["review_run_events", "retry_or_revise"],
            },
        )
        self._event(failed, default_event, item_id=item_id, message=reason, metadata=payload)
        return failed

    def _mark_failed(self, run_id: str, reason: str, exc: Exception) -> AtlasRunState:
        state = self.run_store.patch_state(
            run_id,
            {
                "status": "failed",
                "phase": "final_summary",
                "error": f"{reason}:{exc.__class__.__name__}:{exc}",
                "requires_user_action": True,
                "next_actions": ["review_run_events"],
            },
        )
        self._event(state, "run_failed", message=state.error)
        return state

    @staticmethod
    def _select_item(pool: Any, item_id: str) -> Any:
        if item_id:
            item = pool.get_item(item_id)
            if item is None:
                raise ValueError(f"item_not_found:{item_id}")
            return item
        ready_items = pool.get_ready_items() if hasattr(pool, "get_ready_items") else []
        if ready_items:
            return ready_items[0]
        for item in getattr(pool, "items", []) or []:
            if str(getattr(item, "status", "") or "") in {
                "ready",
                "approval_required",
                "approved",
                "waiting_for_critical_decision",
                "blocked_safety_review",
                "blocked",
                "needs_revision",
            }:
                return item
        raise ValueError("no_runnable_item")

    @staticmethod
    def _item_index(pool: Any, item_id: str) -> int:
        for idx, item in enumerate(getattr(pool, "items", []) or [], start=1):
            if getattr(item, "item_id", "") == item_id:
                return idx
        return 0

    @staticmethod
    def _blocker(pool: Any, item: Any, *, mode: str = "fresh") -> str:
        pool_status = str(getattr(pool, "status", "") or "")
        item_status = str(getattr(item, "status", "") or "")
        if pool_status in {"needs_scope_confirmation", "waiting_for_critical_decision", "blocked_safety_review", "blocked", "failed", "cancelled"}:
            return f"pool_not_runnable:{pool_status}"
        # "resume" must retry the item the run stopped on (failed/blocked) instead of treating that
        # very item as permanently unrunnable — mirrors select_run_items's RESUME_RETRYABLE_STATUSES
        # so both gates agree on what resume may retry.
        blocking_item_statuses = {"waiting_for_critical_decision", "blocked_safety_review", "blocked", "failed", "cancelled", "needs_revision"}
        if str(mode or "").strip() == "resume":
            blocking_item_statuses -= RESUME_RETRYABLE_STATUSES
        if item_status in blocking_item_statuses:
            return f"item_not_runnable:{item_status}"
        pool_critical = dict((getattr(pool, "metadata", {}) or {}).get("critical_event") or {})
        item_critical = dict((getattr(item, "metadata", {}) or {}).get("critical_event") or {})
        if pool_critical.get("critical_event") or item_critical.get("critical_event"):
            return "critical_event_waiting_for_user_decision"
        return ""

    @staticmethod
    def _proposal_id(payload: dict[str, Any]) -> str:
        proposal = payload.get("proposal") if isinstance(payload.get("proposal"), dict) else {}
        return str(proposal.get("proposal_id") or payload.get("proposal_id") or "")

    @staticmethod
    def _dump(value: Any) -> dict[str, Any]:
        if hasattr(value, "model_dump"):
            return value.model_dump()
        if isinstance(value, dict):
            return dict(value)
        return {"value": value}
