from __future__ import annotations

from enum import StrEnum


class PlaySessionState(StrEnum):
    CREATED = "created"
    RESOLVING_TARGET = "resolving_target"
    RESOLVING_ENVIRONMENT = "resolving_environment"
    PREPARING = "preparing"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"
    RECOVERABLE = "recoverable"
    EXPIRED = "expired"
    PURGED = "purged"


class PlaySessionEvent(StrEnum):
    RESOLVE_TARGET = "resolve_target"
    TARGET_RESOLVED = "target_resolved"
    ENVIRONMENT_RESOLVED = "environment_resolved"
    PREPARED = "prepared"
    STARTED = "started"
    STOP_REQUESTED = "stop_requested"
    STOPPED = "stopped"
    FAILED = "failed"
    DISCONNECTED_WITH_DATA = "disconnected_with_data"
    RECOVERED = "recovered"
    EXPIRED = "expired"
    PURGED = "purged"


_TERMINAL_STATES = {
    PlaySessionState.STOPPED,
    PlaySessionState.FAILED,
    PlaySessionState.EXPIRED,
    PlaySessionState.PURGED,
}

_TRANSITIONS: dict[tuple[PlaySessionState, PlaySessionEvent], PlaySessionState] = {
    (PlaySessionState.CREATED, PlaySessionEvent.RESOLVE_TARGET): PlaySessionState.RESOLVING_TARGET,
    (PlaySessionState.RESOLVING_TARGET, PlaySessionEvent.TARGET_RESOLVED): PlaySessionState.RESOLVING_ENVIRONMENT,
    (PlaySessionState.RESOLVING_ENVIRONMENT, PlaySessionEvent.ENVIRONMENT_RESOLVED): PlaySessionState.PREPARING,
    (PlaySessionState.PREPARING, PlaySessionEvent.PREPARED): PlaySessionState.STARTING,
    (PlaySessionState.STARTING, PlaySessionEvent.STARTED): PlaySessionState.RUNNING,
    (PlaySessionState.RUNNING, PlaySessionEvent.STOP_REQUESTED): PlaySessionState.STOPPING,
    (PlaySessionState.STOPPING, PlaySessionEvent.STOPPED): PlaySessionState.STOPPED,
    (PlaySessionState.RUNNING, PlaySessionEvent.DISCONNECTED_WITH_DATA): PlaySessionState.RECOVERABLE,
    (PlaySessionState.RECOVERABLE, PlaySessionEvent.RECOVERED): PlaySessionState.RUNNING,
    (PlaySessionState.RECOVERABLE, PlaySessionEvent.STOP_REQUESTED): PlaySessionState.STOPPING,
    (PlaySessionState.RECOVERABLE, PlaySessionEvent.EXPIRED): PlaySessionState.EXPIRED,
    (PlaySessionState.STOPPED, PlaySessionEvent.PURGED): PlaySessionState.PURGED,
    (PlaySessionState.FAILED, PlaySessionEvent.PURGED): PlaySessionState.PURGED,
    (PlaySessionState.EXPIRED, PlaySessionEvent.PURGED): PlaySessionState.PURGED,
}

for _state in (
    PlaySessionState.CREATED,
    PlaySessionState.RESOLVING_TARGET,
    PlaySessionState.RESOLVING_ENVIRONMENT,
    PlaySessionState.PREPARING,
    PlaySessionState.STARTING,
    PlaySessionState.RUNNING,
    PlaySessionState.STOPPING,
    PlaySessionState.RECOVERABLE,
):
    _TRANSITIONS[(_state, PlaySessionEvent.FAILED)] = PlaySessionState.FAILED


def reduce_play_session_state(
    current: PlaySessionState | str,
    event: PlaySessionEvent | str,
) -> PlaySessionState:
    """Return the next lifecycle state without touching process or filesystem state."""
    current_state = PlaySessionState(current)
    event_type = PlaySessionEvent(event)
    if current_state in _TERMINAL_STATES and event_type != PlaySessionEvent.PURGED:
        raise ValueError(f"terminal_state_transition_rejected:{current_state}:{event_type}")
    try:
        return _TRANSITIONS[(current_state, event_type)]
    except KeyError as exc:
        raise ValueError(f"invalid_play_session_transition:{current_state}:{event_type}") from exc
