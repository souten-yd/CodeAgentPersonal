"""Architecture Blueprint persistence (PI-2).

Isolated SQLite store for immutable Blueprint revisions. It is a private module-internal
adapter: the facade returns DTOs only and no consumer queries these tables (ADR-PI-015).
It does not touch PlanPool, Conversation, Nexus or Memory canonical data.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from agent.architecture_blueprint.migrations import (
    BLUEPRINT_TABLE,
    MIGRATION_TABLE,
    SCHEMA_MIGRATIONS,
)
from agent.project_intelligence._persistence import (
    ArtifactStore,
    StoreError,
    apply_migrations,
    connect,
    default_sqlite_path,
)

__all__ = ["BlueprintStore", "StoreError"]


class BlueprintStore:
    """Immutable, revisioned, project-isolated Blueprint revision store."""

    def __init__(self, db_path: str | Path | None = None, *, now_fn: Callable[[], str] | None = None) -> None:
        self._conn = connect(db_path or default_sqlite_path("blueprint"))
        apply_migrations(self._conn, SCHEMA_MIGRATIONS, migration_table=MIGRATION_TABLE)
        self._artifacts = ArtifactStore(self._conn, BLUEPRINT_TABLE, now_fn=now_fn)

    def save_revision(
        self,
        *,
        project_id: str,
        workspace_id: str,
        blueprint_id: str,
        revision_id: str,
        payload: dict[str, Any],
        parent_revision_id: str | None = None,
        expected_parent_id: str | None = None,
        status: str = "draft",
        idempotency_key: str | None = None,
        advance_head: bool = True,
    ) -> str:
        """Persist an immutable Blueprint revision.

        ``advance_head`` defaults True (the head tracks the latest saved revision). The
        Blueprint module passes ``advance_head=False`` for proposed/child revisions and
        selects the active revision explicitly via :meth:`activate_revision`, so a proposed
        or rejected child never becomes active just by being saved.
        """
        return self._artifacts.put(
            project_id=project_id,
            workspace_id=workspace_id,
            group_id=blueprint_id,
            artifact_id=revision_id,
            artifact_type="blueprint_revision",
            payload=payload,
            status=status,
            parent_artifact_id=parent_revision_id,
            expected_parent_id=expected_parent_id,
            idempotency_key=idempotency_key,
            advance_head=advance_head,
        )

    def activate_revision(self, *, project_id: str, workspace_id: str, blueprint_id: str, revision_id: str) -> None:
        """Make an existing revision the active (head) one for its blueprint."""
        self._artifacts.set_head(project_id, workspace_id, blueprint_id, revision_id)

    def set_revision_status(self, *, project_id: str, revision_id: str, status: str) -> None:
        self._artifacts.set_status(project_id, revision_id, status)

    def get_revision(self, project_id: str, revision_id: str) -> dict[str, Any] | None:
        return self._artifacts.get(project_id, revision_id)

    def get_active(self, project_id: str, workspace_id: str, blueprint_id: str) -> dict[str, Any] | None:
        return self._artifacts.get_head(project_id, workspace_id, blueprint_id)

    def get_active_for_workspace(self, project_id: str, workspace_id: str) -> dict[str, Any] | None:
        heads = self._artifacts.list_heads(project_id, workspace_id)
        return heads[0] if heads else None

    def list_revisions(self, project_id: str, blueprint_id: str) -> list[dict[str, Any]]:
        return self._artifacts.list_history(project_id, blueprint_id)

    def revision_as_of(self, project_id: str, blueprint_id: str, as_of_iso: str) -> dict[str, Any] | None:
        return self._artifacts.point_in_time(project_id, blueprint_id, as_of_iso)

    def integrity_check(self, project_id: str) -> dict[str, Any]:
        return self._artifacts.integrity_check(project_id)

    def close(self) -> None:
        self._conn.close()
