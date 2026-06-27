from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from pydantic import BaseModel, Field

from agent.atlas_run_events import validate_run_storage_id
from agent.atlas_run_locks import acquire_run_lease, refresh_run_heartbeat, release_run_lease
from agent.atlas_run_orchestrator import (
    AtlasRunOrchestrator,
    AtlasRunOrchestratorCallbacks,
    AtlasRunOrchestratorRequest,
)
from agent.atlas_run_recovery import recover_stale_runs
from agent.atlas_run_retry_policy import retry_decision
from agent.atlas_run_schema import AtlasRunState, TERMINAL_RUN_STATUSES
from agent.atlas_run_store import AtlasRunStore
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
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


class AtlasRunRecoverRequest(BaseModel):
    stale_after_seconds: int = 900


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


def _current_llm_max_ctx(request: Request) -> int:
    provider = getattr(getattr(request, "app", None), "state", None)
    provider = getattr(provider, "runtime_llm_props_provider", None)
    if not callable(provider):
        return 0
    try:
        props = provider() or {}
        return max(0, int(props.get("n_ctx_runtime") or props.get("n_ctx") or 0))
    except Exception:
        return 0


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return max(0, int(value))
    except Exception:
        return None


def _find_first_int(payload: Any, keys: set[str]) -> int | None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key) in keys:
                found = _int_or_none(value)
                if found is not None:
                    return found
        for value in payload.values():
            found = _find_first_int(value, keys)
            if found is not None:
                return found
    if isinstance(payload, list):
        for value in payload:
            found = _find_first_int(value, keys)
            if found is not None:
                return found
    return None


def _token_usage_from_payload(payload: Any) -> dict[str, int]:
    generated = _find_first_int(payload, {"generated_tokens", "tokens_generated", "tokens_total", "output_tokens"})
    context = _find_first_int(payload, {"context_tokens", "prompt_tokens", "input_tokens"})
    max_ctx = _find_first_int(payload, {"max_context_tokens", "max_ctx", "n_ctx_runtime", "n_ctx"})
    usage: dict[str, int] = {}
    if generated is not None:
        usage["generated_tokens"] = generated
    if context is not None:
        usage["context_tokens"] = context
    if max_ctx is not None:
        usage["max_context_tokens"] = max_ctx
    return usage


def _item_patch_generation_sources(pool: Any, state: AtlasRunState) -> list[Any]:
    sources: list[Any] = []
    if pool is None:
        return sources
    current_item_id = str(state.current_item_id or "")
    for item in getattr(pool, "items", []) or []:
        if current_item_id and str(getattr(item, "item_id", "")) != current_item_id:
            continue
        metadata = getattr(item, "metadata", {}) or {}
        patch_generation = metadata.get("patch_generation") if isinstance(metadata, dict) else None
        if isinstance(patch_generation, dict):
            sources.append(patch_generation)
    return sources


def _run_token_usage(store: AtlasRunStore, state: AtlasRunState, request: Request, pool: Any) -> dict[str, int]:
    sources: list[Any] = []
    try:
        sources.extend(event.model_dump() for event in reversed(store.read_events(state.run_id, after_sequence=0, limit=1000)))
    except Exception:
        pass
    metadata = dict(state.metadata or {})
    sources.extend([metadata, metadata.get("patch_generation"), metadata.get("last_apply_verify_result")])
    sources.extend(_item_patch_generation_sources(pool, state))
    usage: dict[str, int] = {}
    for source in sources:
        if not source:
            continue
        candidate = _token_usage_from_payload(source)
        if candidate:
            usage.update(candidate)
            break
    generated = int(usage.get("generated_tokens") or 0)
    context = int(usage.get("context_tokens") or 0)
    max_ctx = int(usage.get("max_context_tokens") or 0) or _current_llm_max_ctx(request)
    return {
        "generated_tokens": generated,
        "tokens_generated": generated,
        "context_tokens": context,
        "max_context_tokens": max_ctx,
        "max_ctx": max_ctx,
    }


def _load_plan_pool_for_run(root_dir: Any, state: AtlasRunState) -> Any | None:
    try:
        return AtlasPlanPoolStorage(root_dir).load_pool(state.pool_id)
    except Exception:
        return None


def _run_item_status(item_id: str, state: AtlasRunState) -> str:
    if item_id in set(state.completed_item_ids or []):
        return "completed"
    if item_id in set(state.failed_item_ids or []):
        return "failed"
    if item_id in set(state.blocked_item_ids or []):
        return "blocked"
    if item_id in set(state.skipped_item_ids or []):
        return "skipped"
    if item_id == state.current_item_id and state.status == "running":
        return "running"
    return "pending"


def _run_item_progress(pool: Any, state: AtlasRunState) -> list[dict[str, str]]:
    if pool is None:
        return []
    rows: list[dict[str, str]] = []
    for item in getattr(pool, "items", []) or []:
        item_id = str(getattr(item, "item_id", "") or "")
        if not item_id:
            continue
        status = _run_item_status(item_id, state)
        rows.append(
            {
                "item_id": item_id,
                "title": str(getattr(item, "title", "") or getattr(item, "goal", "") or item_id),
                "status": status,
                "phase": str(state.phase or "") if status != "pending" else "",
            }
        )
    return rows


def _lease_owner(run_id: str) -> str:
    return f"atlas_run_worker:{run_id}:{uuid4().hex[:8]}"


def _start_payload_with_lease(payload: AtlasRunStartRequest, *, lease_owner: str) -> AtlasRunStartRequest:
    return AtlasRunStartRequest(
        item_id=payload.item_id,
        item_ids=list(payload.item_ids or []),
        mode=payload.mode,
        preset_id=payload.preset_id,
        command_id=payload.command_id,
        metadata={**_scrub_metadata(payload.metadata), "lease_owner": lease_owner},
    )


def _acquire_or_raise(store: AtlasRunStore, run_id: str, *, owner: str) -> AtlasRunState:
    lease = acquire_run_lease(store, run_id, owner=owner)
    if not lease.acquired:
        raise _api_error(409, lease.reason or "run_already_active", lease.reason or "run_already_active")
    return lease.state


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
        owner = _lease_owner(state.run_id)
        state = _acquire_or_raise(store, state.run_id, owner=owner)
        background_tasks.add_task(_run_one_item, request, state.run_id, _start_payload_with_lease(start_payload, lease_owner=owner))
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
    root_dir = resolve_atlas_ca_data_root(request)
    store = AtlasRunStore(root_dir)
    state = _load_state(store, run_id)
    pool = _load_plan_pool_for_run(root_dir, state)
    completed_item_ids = list(state.completed_item_ids or [])
    failed_item_ids = list(state.failed_item_ids or [])
    blocked_item_ids = list(state.blocked_item_ids or [])
    skipped_item_ids = list(state.skipped_item_ids or [])
    return {
        "run_id": state.run_id,
        "pool_id": state.pool_id,
        "workspace_id": state.workspace_id,
        "status": state.status,
        "phase": state.phase,
        "current_item_id": state.current_item_id,
        "current_item_index": state.current_item_index,
        "total_items": state.total_items,
        "completed_item_ids": completed_item_ids,
        "failed_item_ids": failed_item_ids,
        "blocked_item_ids": blocked_item_ids,
        "skipped_item_ids": skipped_item_ids,
        "completed_count": len(completed_item_ids),
        "failed_count": len(failed_item_ids),
        "blocked_count": len(blocked_item_ids),
        "skipped_count": len(skipped_item_ids),
        "running_count": 1 if state.status == "running" and state.current_item_id else 0,
        "item_progress": _run_item_progress(pool, state),
        "token_usage": _run_token_usage(store, state, request, pool),
        "requires_user_action": state.requires_user_action,
        "block_reason": state.block_reason,
        "error": state.error,
        "next_actions": state.next_actions,
        "retry_count": state.retry_count,
        "max_retries": state.max_retries,
        "last_retry_reason": state.last_retry_reason,
        "revision_requested_at": state.revision_requested_at,
        "revision_note": state.revision_note,
        "lease_owner": state.lease_owner,
        "lease_acquired_at": state.lease_acquired_at,
        "lease_expires_at": state.lease_expires_at,
        "worker_heartbeat_at": state.worker_heartbeat_at,
        "resume_after_restart_supported": state.resume_after_restart_supported,
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
    owner = _lease_owner(state.run_id)
    leased = _acquire_or_raise(store, state.run_id, owner=owner)
    background_tasks.add_task(_run_one_item, request, state.run_id, _start_payload_with_lease(payload, lease_owner=owner))
    return {
        "run_id": state.run_id,
        "status": "accepted",
        "execution_started": True,
        "state": _state_payload(leased),
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
    owner = _lease_owner(state.run_id)
    _acquire_or_raise(store, state.run_id, owner=owner)
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
    start_payload = AtlasRunStartRequest(
        mode=decision.mode,
        metadata={"retry_reason": payload.reason, **dict(clean_metadata or {}), "lease_owner": owner},
    )
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


@router.post("/recover-stale")
def recover_stale(payload: AtlasRunRecoverRequest, request: Request) -> dict[str, Any]:
    result = recover_stale_runs(resolve_atlas_ca_data_root(request), stale_after_seconds=payload.stale_after_seconds)
    return {"status": "ok", **result}


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
    owner = str((payload.metadata or {}).get("lease_owner") or "")
    try:
        refresh_run_heartbeat(store, run_id, owner=owner)
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
        if run_request.item_id and not run_request.item_ids and run_request.mode not in {"resume", "rerun"}:
            orchestrator.run_one_item(run_request)
        else:
            orchestrator.run_items(run_request)
    finally:
        release_run_lease(store, run_id, owner=owner)


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
