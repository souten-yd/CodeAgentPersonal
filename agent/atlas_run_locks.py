from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import threading

from agent.atlas_run_schema import AtlasRunState
from agent.atlas_run_store import AtlasRunStore
from agent.atlas_time_utils import utc_now_iso


_PROCESS_LOCKS: dict[str, threading.Lock] = {}
_PROCESS_LOCKS_GUARD = threading.Lock()


@dataclass(frozen=True)
class AtlasRunLeaseResult:
    acquired: bool
    state: AtlasRunState
    reason: str = ""
    owner: str = ""


def acquire_run_lease(store: AtlasRunStore, run_id: str, *, owner: str, ttl_seconds: int = 900) -> AtlasRunLeaseResult:
    lock = _process_lock(run_id)
    with lock:
        state = store.load_state(run_id)
        active_reason = _active_start_reason(state)
        if active_reason:
            return AtlasRunLeaseResult(False, state, active_reason, owner)
        now = utc_now_iso()
        expires = _dt_to_iso(_now() + timedelta(seconds=max(1, int(ttl_seconds or 900))))
        leased = store.patch_state(
            run_id,
            {
                "lease_owner": owner,
                "lease_acquired_at": now,
                "lease_expires_at": expires,
                "worker_heartbeat_at": now,
                "resume_after_restart_supported": True,
            },
        )
        store.append_event(
            run_id,
            event_type="run_lease_acquired",
            phase=leased.phase,
            status=leased.status,
            metadata={"lease_owner": owner, "lease_expires_at": expires},
        )
        return AtlasRunLeaseResult(True, leased, owner=owner)


def refresh_run_heartbeat(store: AtlasRunStore, run_id: str, *, owner: str = "", ttl_seconds: int = 900) -> AtlasRunState:
    now = utc_now_iso()
    expires = _dt_to_iso(_now() + timedelta(seconds=max(1, int(ttl_seconds or 900))))
    patch = {
        "worker_heartbeat_at": now,
        "lease_expires_at": expires,
        "resume_after_restart_supported": True,
    }
    if owner:
        patch["lease_owner"] = owner
    return store.patch_state(run_id, patch, heartbeat_only=True)


def release_run_lease(store: AtlasRunStore, run_id: str, *, owner: str = "") -> AtlasRunState:
    lock = _process_lock(run_id)
    with lock:
        state = store.load_state(run_id)
        if owner and state.lease_owner and state.lease_owner != owner:
            return state
        released = store.patch_state(run_id, {"lease_owner": "", "lease_expires_at": ""})
        store.append_event(
            run_id,
            event_type="run_lease_released",
            phase=released.phase,
            status=released.status,
            metadata={"lease_owner": owner or state.lease_owner},
        )
        return released


def is_lease_stale(state: AtlasRunState, *, stale_after_seconds: int = 900) -> bool:
    if state.status not in {"queued", "running"}:
        return False
    now = _now()
    expires = _parse_iso(state.lease_expires_at)
    if expires and expires < now:
        return True
    heartbeat = _parse_iso(state.worker_heartbeat_at)
    if heartbeat and heartbeat + timedelta(seconds=max(1, int(stale_after_seconds or 900))) < now:
        return True
    return False


def _active_start_reason(state: AtlasRunState) -> str:
    if state.status == "running":
        if is_lease_stale(state):
            return "stale_run_requires_recovery"
        return "run_already_active"
    if state.status == "queued" and state.lease_owner and not is_lease_stale(state):
        return "run_already_active"
    if state.status == "queued" and state.lease_owner and is_lease_stale(state):
        return "stale_run_requires_recovery"
    return ""


def _process_lock(run_id: str) -> threading.Lock:
    with _PROCESS_LOCKS_GUARD:
        return _PROCESS_LOCKS.setdefault(run_id, threading.Lock())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _dt_to_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_iso(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None
