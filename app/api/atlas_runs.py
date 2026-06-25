from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from agent.atlas_run_events import validate_run_storage_id
from agent.atlas_run_schema import AtlasRunState, TERMINAL_RUN_STATUSES
from agent.atlas_run_store import AtlasRunStore
from app.api.atlas_root import resolve_atlas_ca_data_root


router = APIRouter(prefix="/api/atlas/runs", tags=["atlas-runs"])

_SECRET_KEY_MARKERS = ("secret", "token", "password", "credential", "api_key", "apikey", "auth")


class AtlasRunCreateRequest(BaseModel):
    pool_id: str
    workspace_id: str = "default"
    mode: str = "fresh"
    run_id: str = ""
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
def create_run(payload: AtlasRunCreateRequest, request: Request) -> dict[str, Any]:
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
    return {
        "run_id": state.run_id,
        "state": _state_payload(state),
        "execution_started": False,
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
def retry_run(run_id: str, payload: AtlasRunControlRequest, request: Request) -> dict[str, Any]:
    return _record_deferred_control(run_id=run_id, payload=payload, request=request, event_type="run_retry_requested")


@router.post("/{run_id}/revise")
def revise_run(run_id: str, payload: AtlasRunControlRequest, request: Request) -> dict[str, Any]:
    return _record_deferred_control(run_id=run_id, payload=payload, request=request, event_type="run_revise_requested")
