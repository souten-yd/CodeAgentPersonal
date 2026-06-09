"""Twin event envelope and the initial event-type catalog (PDT-1).

Events are how producers (workspace, Safe Apply, PlanPool, verification, runtime
collectors, conversation, memory, skill, Nexus) notify the twin. Every event carries a
contract version and an idempotency key so projection is replay-safe.

No storage dependency.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from agent.project_twin.types import CONTRACT_VERSION

#: Initial event-type catalog. Tolerant readers must accept additive members.
EVENT_TYPES: frozenset[str] = frozenset(
    {
        "workspace.changed",
        "safe_apply.completed",
        "plan_item.completed",
        "verification.completed",
        "runtime_observation.recorded",
        "conversation.message.completed",
        "requirement.confirmed",
        "memory.promoted",
        "memory.superseded",
        "skill.registered",
        "skill.activated",
        "nexus.evidence.added",
    }
)


class TwinEventEnvelope(BaseModel):
    event_id: str
    event_type: str
    contract_version: str = CONTRACT_VERSION
    project_id: str
    source: str
    source_ref: str | None = None
    occurred_at: datetime
    idempotency_key: str
    payload: dict[str, Any] = Field(default_factory=dict)


def make_event_envelope(
    *,
    event_id: str,
    event_type: str,
    project_id: str,
    source: str,
    idempotency_key: str,
    source_ref: str | None = None,
    occurred_at: datetime | None = None,
    payload: dict[str, Any] | None = None,
) -> TwinEventEnvelope:
    """Build an envelope, defaulting ``occurred_at`` to now (UTC)."""

    return TwinEventEnvelope(
        event_id=event_id,
        event_type=event_type,
        project_id=project_id,
        source=source,
        source_ref=source_ref,
        occurred_at=occurred_at or datetime.now(timezone.utc),
        idempotency_key=idempotency_key,
        payload=payload or {},
    )
