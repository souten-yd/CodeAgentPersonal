from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


ACTIVE_PATCH_GENERATION_STATES = {"queued", "running", "validating", "repairing", "retrying"}
TERMINAL_PATCH_GENERATION_STATES = {"succeeded", "failed", "blocked", "cancelled"}
SUCCESS_PATCH_GENERATION_OUTCOMES = {"success"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_patch_generation_state(*, run_id: str = "") -> dict[str, Any]:
    return {
        "schema_version": "atlas.patch_generation_state.v1",
        "run_id": run_id,
        "state": "not_started",
        "outcome": "none",
        "attempt": 0,
        "strategy": "",
        "reason_code": "",
        "retryable": False,
        "candidate_fingerprint": "",
        "failure_signature": "",
        "patch_content_available": False,
        "passed_checks": [],
        "failed_checks": [],
        "diagnostics": [],
        "history": [],
        "updated_at": utc_now_iso(),
    }


def reduce_patch_generation_state(current: dict[str, Any] | None, event: dict[str, Any]) -> dict[str, Any]:
    """Pure reducer for patch-generation state.

    This function intentionally performs no IO and mutates neither the input state nor
    the event payload. Persistence is handled by the service-level transition boundary.
    """
    state = deepcopy(current) if isinstance(current, dict) and current else default_patch_generation_state()
    event_payload = deepcopy(event or {})
    run_id = str(event_payload.get("run_id") or state.get("run_id") or "")
    event_type = str(event_payload.get("event_type") or event_payload.get("type") or "")
    next_state = str(event_payload.get("state") or _state_from_event_type(event_type) or state.get("state") or "not_started")
    outcome = str(event_payload.get("outcome") or _outcome_from_state(next_state) or state.get("outcome") or "none")

    state["run_id"] = run_id
    state["state"] = next_state
    state["outcome"] = outcome
    state["attempt"] = int(event_payload.get("attempt", state.get("attempt") or 0) or 0)
    state["strategy"] = str(event_payload.get("strategy") or state.get("strategy") or "")
    state["reason_code"] = str(event_payload.get("reason_code") or event_payload.get("reason") or state.get("reason_code") or "")
    state["retryable"] = bool(event_payload.get("retryable", state.get("retryable", False)))
    state["candidate_fingerprint"] = str(event_payload.get("candidate_fingerprint") or state.get("candidate_fingerprint") or "")
    state["failure_signature"] = str(event_payload.get("failure_signature") or state.get("failure_signature") or "")
    state["patch_content_available"] = bool(event_payload.get("patch_content_available", state.get("patch_content_available", False)))
    state["passed_checks"] = list(event_payload.get("passed_checks") or state.get("passed_checks") or [])
    state["failed_checks"] = list(event_payload.get("failed_checks") or state.get("failed_checks") or [])
    diagnostics = list(state.get("diagnostics") or [])
    diagnostics.extend(list(event_payload.get("diagnostics") or []))
    state["diagnostics"] = diagnostics[-50:]
    history = list(state.get("history") or [])
    history.append(_compact_history_event(event_payload, next_state, outcome))
    state["history"] = history[-50:]
    state["updated_at"] = str(event_payload.get("created_at") or event_payload.get("timestamp") or utc_now_iso())
    return state


def is_patch_generation_success(value: dict[str, Any] | None) -> bool:
    if not isinstance(value, dict):
        return False
    return (
        str(value.get("state") or "").lower() == "succeeded"
        and str(value.get("outcome") or "").lower() in SUCCESS_PATCH_GENERATION_OUTCOMES
        and bool(value.get("patch_content_available"))
    )


def is_patch_generation_active(value: dict[str, Any] | None) -> bool:
    return isinstance(value, dict) and str(value.get("state") or "").lower() in ACTIVE_PATCH_GENERATION_STATES


def is_patch_generation_terminal(value: dict[str, Any] | None) -> bool:
    return isinstance(value, dict) and str(value.get("state") or "").lower() in TERMINAL_PATCH_GENERATION_STATES


def _state_from_event_type(event_type: str) -> str:
    mapping = {
        "patch_generation_queued": "queued",
        "patch_generation_started": "running",
        "patch_candidate_generated": "validating",
        "patch_validation_failed": "repairing",
        "patch_repair_started": "repairing",
        "patch_candidate_repaired": "validating",
        "patch_retry_started": "retrying",
        "patch_validation_passed": "validating",
        "patch_generation_succeeded": "succeeded",
        "patch_generation_failed": "failed",
        "patch_generation_blocked": "blocked",
        "patch_generation_cancelled": "cancelled",
    }
    return mapping.get(event_type, "")


def _outcome_from_state(state: str) -> str:
    if state == "succeeded":
        return "success"
    if state == "failed":
        return "failure"
    if state == "blocked":
        return "blocked"
    if state == "cancelled":
        return "cancelled"
    if state in ACTIVE_PATCH_GENERATION_STATES:
        return "active"
    return "none"


def _compact_history_event(event: dict[str, Any], state: str, outcome: str) -> dict[str, Any]:
    return {
        "event_type": str(event.get("event_type") or event.get("type") or ""),
        "run_id": str(event.get("run_id") or ""),
        "state": state,
        "outcome": outcome,
        "attempt": int(event.get("attempt", 0) or 0),
        "strategy": str(event.get("strategy") or ""),
        "reason_code": str(event.get("reason_code") or event.get("reason") or ""),
        "created_at": str(event.get("created_at") or event.get("timestamp") or utc_now_iso()),
    }
