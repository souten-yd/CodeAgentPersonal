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
)

__all__ = ["BlueprintStore", "StoreError"]


class BlueprintStore:
    """Immutable, revisioned, project-isolated Blueprint revision store."""

    def __init__(self, db_path: str | Path = ":memory:", *, now_fn: Callable[[], str] | None = None) -> None:
        self._conn = connect(db_path)
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
    ) -> str:
        """Persist an immutable Blueprint revision and advance the blueprint head."""
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
        )

    def get_revision(self, project_id: str, revision_id: str) -> dict[str, Any] | None:
        return self._artifacts.get(project_id, revision_id)

    def get_active(self, project_id: str, workspace_id: str, blueprint_id: str) -> dict[str, Any] | None:
        return self._artifacts.get_head(project_id, workspace_id, blueprint_id)

    def list_revisions(self, project_id: str, blueprint_id: str) -> list[dict[str, Any]]:
        return self._artifacts.list_history(project_id, blueprint_id)

    def revision_as_of(self, project_id: str, blueprint_id: str, as_of_iso: str) -> dict[str, Any] | None:
        return self._artifacts.point_in_time(project_id, blueprint_id, as_of_iso)

    def integrity_check(self, project_id: str) -> dict[str, Any]:
        return self._artifacts.integrity_check(project_id)

    def close(self) -> None:
        self._conn.close()
