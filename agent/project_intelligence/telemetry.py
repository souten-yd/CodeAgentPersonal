"""Project Intelligence rollout telemetry (PI-3).

A minimal, side-effect-free telemetry sink. In shadow mode the coordinator records
comparison artifacts here; these are observational only and never alter Planner/Generator
inputs (ADR-PI-017). The default sink keeps records in memory; a real sink can persist
them, but recording must never change a returned context package.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class TelemetryRecord:
    event_type: str
    phase: str
    rollout_mode: str
    project_id: str
    workspace_id: str
    detail: dict[str, Any] = field(default_factory=dict)
    recorded_at: str = field(default_factory=_utcnow_iso)


class TelemetrySink:
    """In-memory telemetry sink. Recording is observational and order-preserving."""

    def __init__(self) -> None:
        self._records: list[TelemetryRecord] = []

    def record(
        self,
        *,
        event_type: str,
        phase: str,
        rollout_mode: str,
        project_id: str,
        workspace_id: str,
        detail: dict[str, Any] | None = None,
    ) -> TelemetryRecord:
        rec = TelemetryRecord(
            event_type=event_type,
            phase=phase,
            rollout_mode=rollout_mode,
            project_id=project_id,
            workspace_id=workspace_id,
            detail=dict(detail or {}),
        )
        self._records.append(rec)
        return rec

    def records(self, *, event_type: str | None = None) -> list[TelemetryRecord]:
        if event_type is None:
            return list(self._records)
        return [r for r in self._records if r.event_type == event_type]

    def comparison_artifacts(self) -> list[TelemetryRecord]:
        return self.records(event_type="shadow_comparison")

    def clear(self) -> None:
        self._records.clear()
