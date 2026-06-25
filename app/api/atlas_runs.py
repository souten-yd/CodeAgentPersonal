from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from pydantic import BaseModel, Field

from agent.atlas_run_events import validate_run_storage_id
from agent.atlas_run_orchestrator import (
    AtlasRunOrchestrator,
    AtlasRunOrchestratorCallbacks,
    AtlasRunOrchestratorRequest,
)
from agent.atlas_run_retry_policy import retry_decision
from agent.atlas_run_schema import AtlasRunState, TERMINAL_RUN_STATUSES
from agent.atlas_run_store import AtlasRunStore
from agent.atlas_time_utils import utc_now_iso
from app.api.atlas_root import resolve_atlas_ca_data_root


router = APIRouter(prefix="/api/atlas/runs", tags=["atlas-runs"])

_SECRET_KEY_MARKERS = ("secret", "token", "password", "credential", "api_key", "apikey", "auth")


class AtlasRunCreateRequest(BaseModel):
    pool_id: str
    workspace_id: str = "default"
    mode: str = "fresh"
    run_id: str = ""
    item_id: str = ""
    auto_start: bool = False
    preset_id: str = "guarded_low_risk"
    command_id: str = ""
    item_ids: list[str] = Field(default_factory=list)
    total_items: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class AtlasRunDecisionRequest(BaseModel):
    decision_type: str = "operator_decision"
    decision: str
    item_id: str = ""
    reason: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class AtlasRunControlRequest(BaseModel):
    reason: str = ""
    mode: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class AtlasRunStartRequest(BaseModel):
    item_id: str = ""
    item_ids: list[str] = Field(default_factory=list)
    mode: str = ""
    preset_id: str = "guarded_low_risk"
    command_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


def _store(request: Request) -> AtlasRunStore:
    return AtlasRunStore(resolve_atlas_ca_data_root(request))


def _api_error(status_code: int, error: str, reason: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"error": error, "reason": reason})


def _validate_storage_id(value: str, field_name: str) -> str:
    try:
        return validate_run_storage_id(value, field_name)
    except ValueError as exc:
        raise _api_error(400, "invalid_request", str(exc)) from exc


def _load_state(store: AtlasRunStore, run_id: str) -> AtlasRunState:
    safe_run_id = _validate_storage_id(run_id, "run_id")
    try:
        return store.load_state(safe_run_id)
    except FileNotFoundError as exc:
        raise _api_error(404, "run_not_found", f"run_not_found:{safe_run_id}") from exc
    except Exception as exc:  # noqa: BLE001
        raise _api_error(500, "run_state_unavailable", f"{exc.__class__.__name__}: {exc}") from exc


def _scrub_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key)
            lowered = key.lower()
            if any(marker in lowered for marker in _SECRET_KEY_MARKERS):
                clean[key] = "[redacted]"
            else:
                clean[key] = _scrub_metadata(raw_value)
        return clean
    if isinstance(value, list):
        return [_scrub_metadata(item) for item in value]
    return value


def _state_payload(state: AtlasRunState) -> dict[str, Any]:
    return state.model_dump()


@router.post("")
def create_run(payload: AtlasRunCreateRequest, request: Request, background_tasks: BackgroundTasks) -> dict[str, Any]:
    store = _store(request)
    try:
        if payload.run_id:
            safe_run_id = validate_run_storage_id(payload.run_id, "run_id")
            if store.state_path(safe_run_id).exists():
                raise _api_error(409, "run_already_exists", f"run_already_exists:{safe_run_id}")
        state = store.create_run(
            pool_id=payload.pool_id,
            workspace_id=payload.workspace_id,
            mode=payload.mode,
            run_id=payload.run_id,
            total_items=payload.total_items,
            metadata=_scrub_metadata(payload.metadata),
        )
    except ValueError as exc:
        raise _api_error(400, "invalid_request", str(exc)) from exc
    if payload.auto_start:
        start_payload = AtlasRunStartRequest(
            item_id=payload.item_id,
            item_ids=list(payload.item_ids or []),
            mode=payload.mode,
            preset_id=payload.preset_id,
            command_id=payload.command_id,
            metadata=payload.metadata,
        )
        background_tasks.add_task(_run_one_item, request, state.run_id, start_payload)
    return {
        "run_id": state.run_id,
        "state": _state_payload(state),
        "execution_started": bool(payload.auto_start),
        "authoritative_source": "backend_run_store",
    }


@router.get("/{run_id}")
def get_run(run_id: str, request: Request) -> dict[str, Any]:
    store = _store(request)
    state = _load_state(store, run_id)
    return {"run_id": state.run_id, "state": _state_payload(state)}


@router.get("/{run_id}/status")
def get_run_status(run_id: str, request: Request) -> dict[str, Any]:
    store = _store(request)
    state = _load_state(store, run_id)
    return {
        "run_id": state.run_id,
        "pool_id": state.pool_id,
        "workspace_id": state.workspace_id,
        "status": state.status,
        "phase": state.phase,
        "current_item_id": state.current_item_id,
        "current_item_index": state.current_item_index,
        "total_items": state.total_items,
        "requires_user_action": state.requires_user_action,
        "block_reason": state.block_reason,
        "error": state.error,
        "next_actions": state.next_actions,
        "retry_count": state.retry_count,
        "max_retries": state.max_retries,
        "last_retry_reason": state.last_retry_reason,
        "revision_requested_at": state.revision_requested_at,
        "revision_note": state.revision_note,
        "terminal": state.terminal,
        "updated_at": state.updated_at,
        "finished_at": state.finished_at,
    }


@router.get("/{run_id}/events")
def get_run_events(
    run_id: str,
    request: Request,
    after_sequence: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
) -> dict[str, Any]:
    store = _store(request)
    state = _load_state(store, run_id)
    events = store.read_events(state.run_id, after_sequence=after_sequence, limit=limit)
    next_after_sequence = events[-1].sequence if events else after_sequence
    return {
        "run_id": state.run_id,
        "events": [event.model_dump() for event in events],
        "next_after_sequence": next_after_sequence,
    }


@router.post("/{run_id}/decisions")
def record_run_decision(run_id: str, payload: AtlasRunDecisionRequest, request: Request) -> dict[str, Any]:
    store = _store(request)
    state = _load_state(store, run_id)
    decision_type = str(payload.decision_type or "operator_decision").strip() or "operator_decision"
    if not str(payload.decision or "").strip():
        raise _api_error(400, "invalid_request", "decision must not be empty")
    event = store.append_event(
        state.run_id,
        event_type="run_decision_recorded",
        phase=state.phase,
        status=state.status,
        item_id=payload.item_id,
        message=f"Client decision recorded: {decision_type}.",
        source="client",
        metadata={
            "decision_type": decision_type,
            "decision": payload.decision,
            "reason": payload.reason,
            "metadata": _scrub_metadata(payload.metadata),
            "execution_started": False,
            "safe_apply_invoked": False,
        },
    )
    return {
        "run_id": state.run_id,
        "event": event.model_dump(),
        "execution_started": False,
        "safe_apply_invoked": False,
    }


@router.post("/{run_id}/cancel")
def cancel_run(run_id: str, payload: AtlasRunControlRequest, request: Request) -> dict[str, Any]:
    store = _store(request)
    state = _load_state(store, run_id)
    if state.status not in TERMINAL_RUN_STATUSES:
        state = store.patch_state(
            state.run_id,
            {
                "status": "cancelled",
                "phase": "final_summary",
                "requires_user_action": False,
                "block_reason": str(payload.reason or "cancel_requested"),
            },
        )
    event = store.append_event(
        state.run_id,
        event_type="run_cancel_requested",
        phase=state.phase,
        status=state.status,
        message="Client requested run cancellation.",
        source="client",
        metadata={"reason": payload.reason, "metadata": _scrub_metadata(payload.metadata)},
    )
    return {"run_id": state.run_id, "state": _state_payload(state), "event": event.model_dump()}


@router.post("/{run_id}/start")
def start_run(run_id: str, payload: AtlasRunStartRequest, request: Request, background_tasks: BackgroundTasks) -> dict[str, Any]:
    store = _store(request)
    state = _load_state(store, run_id)
    if state.status in TERMINAL_RUN_STATUSES:
        raise _api_error(409, "run_terminal", f"run_terminal:{state.status}")
    background_tasks.add_task(_run_one_item, request, state.run_id, payload)
    return {
        "run_id": state.run_id,
        "status": "accepted",
        "execution_started": True,
        "state": _state_payload(state),
    }


def _record_deferred_control(
    *,
    run_id: str,
    payload: AtlasRunControlRequest,
    request: Request,
    event_type: str,
) -> dict[str, Any]:
    store = _store(request)
    state = _load_state(store, run_id)
    event = store.append_event(
        state.run_id,
        event_type=event_type,
        phase=state.phase,
        status=state.status,
        message=f"Client requested {event_type}; backend orchestration will handle it in a later package.",
        source="client",
        metadata={
            "reason": payload.reason,
            "metadata": _scrub_metadata(payload.metadata),
            "execution_started": False,
            "deferred_to": "server_controlled_orchestrator",
        },
    )
    return {
        "run_id": state.run_id,
        "state": _state_payload(state),
        "event": event.model_dump(),
        "execution_started": False,
        "deferred": True,
    }


@router.post("/{run_id}/retry")
def retry_run(run_id: str, payload: AtlasRunControlRequest, request: Request, background_tasks: BackgroundTasks) -> dict[str, Any]:
    store = _store(request)
    state = _load_state(store, run_id)
    decision = retry_decision(state, requested_mode=payload.mode)
    if not decision.allowed:
        status_code = 400 if decision.reason == "invalid_retry_mode" else 409
        store.append_event(
            state.run_id,
            event_type="run_retry_rejected",
            phase=state.phase,
            status=state.status,
            message=decision.reason,
            source="client",
            metadata={"reason": payload.reason, "mode": payload.mode, "next_actions": decision.next_actions},
        )
        raise _api_error(status_code, decision.reason, decision.reason)
    clean_metadata = _scrub_metadata(payload.metadata)
    retry_count = max(0, int(state.retry_count or 0)) + 1
    requested = store.patch_state(
        state.run_id,
        {
            "status": "running",
            "phase": "planning",
            "mode": decision.mode,
            "requires_user_action": False,
            "block_reason": "",
            "error": "",
            "next_actions": decision.next_actions,
            "retry_count": retry_count,
            "last_retry_reason": str(payload.reason or "operator_retry"),
            "finished_at": "",
            "metadata": {**dict(state.metadata or {}), "last_retry_metadata": clean_metadata},
        },
    )
    request_event = store.append_event(
        requested.run_id,
        event_type="run_retry_requested",
        phase=requested.phase,
        status=requested.status,
        message="Client requested backend run retry.",
        source="client",
        metadata={
            "reason": payload.reason,
            "mode": decision.mode,
            "retry_count": retry_count,
            "max_retries": requested.max_retries,
            "metadata": clean_metadata,
            "execution_started": True,
        },
    )
    store.append_event(
        requested.run_id,
        event_type="run_retry_started",
        phase=requested.phase,
        status=requested.status,
        message="Backend retry execution started.",
        metadata={"mode": decision.mode, "retry_count": retry_count},
    )
    start_payload = AtlasRunStartRequest(mode=decision.mode, metadata={"retry_reason": payload.reason, **dict(clean_metadata or {})})
    background_tasks.add_task(_run_one_item, request, requested.run_id, start_payload)
    return {
        "run_id": requested.run_id,
        "state": _state_payload(requested),
        "event": request_event.model_dump(),
        "execution_started": True,
        "deferred": False,
        "reason": decision.reason,
        "next_actions": decision.next_actions,
    }


@router.post("/{run_id}/revise")
def revise_run(run_id: str, payload: AtlasRunControlRequest, request: Request) -> dict[str, Any]:
    store = _store(request)
    state = _load_state(store, run_id)
    note = str(payload.reason or "").strip()
    if not note:
        note = str((payload.metadata or {}).get("note") or "revise plan").strip()
    clean_metadata = _scrub_metadata(payload.metadata)
    status = state.status if state.status in TERMINAL_RUN_STATUSES else "waiting_for_user"
    revised = store.patch_state(
        state.run_id,
        {
            "status": status,
            "requires_user_action": True,
            "revision_requested_at": utc_now_iso(),
            "revision_note": note,
            "next_actions": ["revise_plan"],
            "metadata": {**dict(state.metadata or {}), "last_revision_metadata": clean_metadata},
        },
    )
    event = store.append_event(
        revised.run_id,
        event_type="run_revise_requested",
        phase=revised.phase,
        status=revised.status,
        message="Client requested plan revision; execution was not started.",
        source="client",
        metadata={
            "reason": payload.reason,
            "mode": payload.mode or "blocked_decision",
            "metadata": clean_metadata,
            "execution_started": False,
            "next_actions": ["revise_plan"],
        },
    )
    return {
        "run_id": revised.run_id,
        "state": _state_payload(revised),
        "event": event.model_dump(),
        "execution_started": False,
        "deferred": False,
        "reason": "revision_note_recorded",
        "next_actions": ["revise_plan"],
    }


def _run_one_item(request: Request, run_id: str, payload: AtlasRunStartRequest) -> None:
    store = _store(request)
    state = store.load_state(run_id)
    run_request = AtlasRunOrchestratorRequest(
        run_id=state.run_id,
        pool_id=state.pool_id,
        workspace_id=state.workspace_id,
        item_id=payload.item_id,
        item_ids=list(payload.item_ids or []),
        mode=payload.mode or state.mode,
        preset_id=payload.preset_id,
        command_id=payload.command_id,
        metadata=_scrub_metadata(payload.metadata),
    )
    orchestrator = _build_run_orchestrator(request, workspace_id=state.workspace_id)
    if run_request.item_ids or run_request.mode in {"resume", "rerun"}:
        orchestrator.run_items(run_request)
    else:
        orchestrator.run_one_item(run_request)


def _build_run_orchestrator(request: Request, *, workspace_id: str) -> AtlasRunOrchestrator:
    from agent.atlas_approval_service import AtlasApprovalService
    from agent.atlas_journal import AtlasJournal
    from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage

    root = resolve_atlas_ca_data_root(request)
    storage = AtlasPlanPoolStorage(root)
    journal = AtlasJournal(root, workspace_id=workspace_id or "default")
    fastapi_request = request

    def _approve_plan_item(*, pool, item, request: AtlasRunOrchestratorRequest) -> dict[str, Any]:
        run_request = request
        result = AtlasApprovalService(journal).decide(
            pool,
            item_id=item.item_id,
            run_id=run_request.run_id,
            decision="approved",
            reason="server_controlled_run_orchestrator",
            approver="atlas_run_orchestrator",
            metadata={"server_controlled_run": True, **dict(run_request.metadata or {})},
        )
        storage.save_pool(pool)
        journal.save_plan_pool(pool)
        return result

    def _generate_patch_proposal(*, pool, item, request: AtlasRunOrchestratorRequest):
        run_request = request
        from agent.atlas_patch_proposal_schema import AtlasPatchProposalRequest
        from app.api.atlas_pipeline import generate_patch_proposal

        return generate_patch_proposal(
            AtlasPatchProposalRequest(
                pool_id=pool.pool_id,
                item_id=item.item_id,
                run_id=run_request.run_id,
                workspace_id=run_request.workspace_id,
                requested_by="atlas_run_orchestrator",
                source_type="plan_item",
                proposal_mode="standard",
                metadata={"server_controlled_run": True, **dict(run_request.metadata or {})},
            ),
            request=fastapi_request,
        )

    def _approve_patch_proposal(*, pool, item, request: AtlasRunOrchestratorRequest, proposal_id: str, proposal: dict[str, Any]):
        run_request = request
        from agent.atlas_patch_proposal_approval_schema import AtlasPatchProposalApprovalRequest
        from app.api.atlas_pipeline import decide_patch_proposal

        return decide_patch_proposal(
            AtlasPatchProposalApprovalRequest(
                pool_id=pool.pool_id,
                item_id=item.item_id,
                proposal_id=proposal_id,
                run_id=run_request.run_id,
                workspace_id=run_request.workspace_id,
                decision="approved",
                reason="server_controlled_run_orchestrator",
                approver="atlas_run_orchestrator",
                metadata={"server_controlled_run": True, **dict(run_request.metadata or {})},
            ),
            request=fastapi_request,
        )

    def _apply_and_verify(*, pool, item, request: AtlasRunOrchestratorRequest, proposal: dict[str, Any]):
        run_request = request
        from app.api.atlas_pipeline import AtlasAutoSafeApplyAndVerifyRequest, atlas_automation_safe_apply_one_and_verify

        return atlas_automation_safe_apply_one_and_verify(
            AtlasAutoSafeApplyAndVerifyRequest(
                pool_id=pool.pool_id,
                item_id=item.item_id,
                preset_id=run_request.preset_id,
                workspace_id=run_request.workspace_id,
                run_id=run_request.run_id,
                command_id=run_request.command_id,
                metadata={"server_controlled_run": True, **dict(run_request.metadata or {})},
            ),
            request=fastapi_request,
        )

    return AtlasRunOrchestrator(
        run_store=_store(request),
        plan_storage=storage,
        journal=journal,
        callbacks=AtlasRunOrchestratorCallbacks(
            approve_plan_item=_approve_plan_item,
            generate_patch_proposal=_generate_patch_proposal,
            approve_patch_proposal=_approve_patch_proposal,
            apply_and_verify=_apply_and_verify,
        ),
    )
