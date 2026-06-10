"""Convergence persistence (PI-2).

Isolated SQLite store for immutable Convergence report history. Private module-internal
adapter; the facade returns DTOs only (ADR-PI-015). It never mutates the workspace,
PlanPool, Blueprint or any canonical Atlas store.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from agent.project_convergence.migrations import (
    CONVERGENCE_TABLE,
    MIGRATION_TABLE,
    SCHEMA_MIGRATIONS,
)
from agent.project_intelligence._persistence import (
    ArtifactStore,
    StoreError,
    apply_migrations,
    connect,
)

__all__ = ["ConvergenceStore", "StoreError"]


class ConvergenceStore:
    """Immutable, project-isolated Convergence report store keyed by blueprint revision."""

    def __init__(self, db_path: str | Path = ":memory:", *, now_fn: Callable[[], str] | None = None) -> None:
        self._conn = connect(db_path)
        apply_migrations(self._conn, SCHEMA_MIGRATIONS, migration_table=MIGRATION_TABLE)
        self._artifacts = ArtifactStore(self._conn, CONVERGENCE_TABLE, now_fn=now_fn)

    def save_report(
        self,
        *,
        project_id: str,
        workspace_id: str,
        blueprint_revision_id: str,
        report_id: str,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> str:
        """Persist an immutable Convergence report; the latest report is the group head."""
        return self._artifacts.put(
            project_id=project_id,
            workspace_id=workspace_id,
            group_id=blueprint_revision_id,
            artifact_id=report_id,
            artifact_type="convergence_report",
            payload=payload,
            status="generated",
            idempotency_key=idempotency_key,
        )

    def get_report(self, project_id: str, report_id: str) -> dict[str, Any] | None:
        return self._artifacts.get(project_id, report_id)

    def get_latest(self, project_id: str, workspace_id: str, blueprint_revision_id: str) -> dict[str, Any] | None:
        return self._artifacts.get_head(project_id, workspace_id, blueprint_revision_id)

    def list_reports(self, project_id: str, blueprint_revision_id: str) -> list[dict[str, Any]]:
        return self._artifacts.list_history(project_id, blueprint_revision_id)

    def integrity_check(self, project_id: str) -> dict[str, Any]:
        return self._artifacts.integrity_check(project_id)

    def close(self) -> None:
        self._conn.close()
