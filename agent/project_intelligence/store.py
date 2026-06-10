"""Project Intelligence persistence (PI-2).

Isolated SQLite store for immutable Context Manifests and a restart-safe job journal.
Private module-internal adapter; the facade returns DTOs only (ADR-PI-015). It stores
references/projections, never competing canonical copies of PlanPool/Conversation/Nexus/
Memory data (ADR-PI-004).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from agent.project_intelligence._persistence import (
    ArtifactStore,
    StoreError,
    apply_migrations,
    connect,
)
from agent.project_intelligence.migrations import (
    JOBS_TABLE,
    MANIFEST_TABLE,
    MIGRATION_TABLE,
    SCHEMA_MIGRATIONS,
)

__all__ = ["ProjectIntelligenceStore", "StoreError"]

_TERMINAL = {"done", "failed", "cancelled"}


class ProjectIntelligenceStore:
    """Context Manifest artifacts (immutable) + a restart-safe job journal (mutable)."""

    def __init__(self, db_path: str | Path = ":memory:", *, now_fn: Callable[[], str] | None = None) -> None:
        self._conn = connect(db_path)
        apply_migrations(self._conn, SCHEMA_MIGRATIONS, migration_table=MIGRATION_TABLE)
        self._now = now_fn or (lambda: datetime.now(timezone.utc).isoformat())
        self._manifests = ArtifactStore(self._conn, MANIFEST_TABLE, now_fn=now_fn)

    # -- context manifests (immutable) ---------------------------------------

    def save_manifest(
        self,
        *,
        project_id: str,
        workspace_id: str,
        phase: str,
        manifest_id: str,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> str:
        return self._manifests.put(
            project_id=project_id,
            workspace_id=workspace_id,
            group_id=phase,
            artifact_id=manifest_id,
            artifact_type="context_manifest",
            payload=payload,
            status="active",
            idempotency_key=idempotency_key,
        )

    def get_manifest(self, project_id: str, manifest_id: str) -> dict[str, Any] | None:
        return self._manifests.get(project_id, manifest_id)

    # -- job journal (restart-safe, ADR-PI-011) ------------------------------

    def enqueue_job(
        self,
        *,
        project_id: str,
        workspace_id: str,
        job_id: str,
        job_type: str,
        payload: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> str:
        """Enqueue a job idempotently. A duplicate idempotency key returns the prior job."""
        if idempotency_key is not None:
            row = self._conn.execute(
                f"SELECT job_id FROM {JOBS_TABLE} WHERE project_id = ? AND idempotency_key = ?",
                (project_id, idempotency_key),
            ).fetchone()
            if row is not None:
                return str(row["job_id"])
        now = self._now()
        payload_json = json.dumps(payload or {}, sort_keys=True, ensure_ascii=False, default=str)
        try:
            self._conn.execute("BEGIN")
            self._conn.execute(
                f"""INSERT INTO {JOBS_TABLE}
                    (job_id, project_id, workspace_id, job_type, status, attempts,
                     idempotency_key, payload, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 'queued', 0, ?, ?, ?, ?)""",
                (job_id, project_id, workspace_id, job_type, idempotency_key, payload_json, now, now),
            )
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        return job_id

    def claim_job(self, project_id: str, job_id: str) -> dict[str, Any] | None:
        """Mark a queued job running and increment attempts. Returns the job or None."""
        now = self._now()
        try:
            self._conn.execute("BEGIN")
            cur = self._conn.execute(
                f"""UPDATE {JOBS_TABLE}
                    SET status = 'running', attempts = attempts + 1, updated_at = ?
                    WHERE project_id = ? AND job_id = ? AND status = 'queued'""",
                (now, project_id, job_id),
            )
            changed = cur.rowcount
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        return self.get_job(project_id, job_id) if changed else None

    def complete_job(self, project_id: str, job_id: str, *, status: str = "done", error: str | None = None) -> None:
        if status not in _TERMINAL:
            raise StoreError("invalid_job_status", status)
        now = self._now()
        try:
            self._conn.execute("BEGIN")
            self._conn.execute(
                f"UPDATE {JOBS_TABLE} SET status = ?, last_error = ?, updated_at = ? WHERE project_id = ? AND job_id = ?",
                (status, error, now, project_id, job_id),
            )
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    def recover_running_jobs(self, project_id: str) -> int:
        """After a restart, requeue jobs left 'running'. Idempotent and crash-safe."""
        now = self._now()
        try:
            self._conn.execute("BEGIN")
            cur = self._conn.execute(
                f"UPDATE {JOBS_TABLE} SET status = 'queued', updated_at = ? WHERE project_id = ? AND status = 'running'",
                (now, project_id),
            )
            n = cur.rowcount
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        return int(n)

    def get_job(self, project_id: str, job_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            f"SELECT * FROM {JOBS_TABLE} WHERE project_id = ? AND job_id = ?",
            (project_id, job_id),
        ).fetchone()
        if not row:
            return None
        return {
            "job_id": row["job_id"],
            "project_id": row["project_id"],
            "workspace_id": row["workspace_id"],
            "job_type": row["job_type"],
            "status": row["status"],
            "attempts": row["attempts"],
            "idempotency_key": row["idempotency_key"],
            "payload": json.loads(row["payload"]),
            "last_error": row["last_error"],
        }

    def list_jobs(self, project_id: str, *, status: str | None = None) -> list[dict[str, Any]]:
        if status is None:
            rows = self._conn.execute(
                f"SELECT job_id FROM {JOBS_TABLE} WHERE project_id = ? ORDER BY created_at ASC",
                (project_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                f"SELECT job_id FROM {JOBS_TABLE} WHERE project_id = ? AND status = ? ORDER BY created_at ASC",
                (project_id, status),
            ).fetchall()
        return [self.get_job(project_id, r["job_id"]) for r in rows]  # type: ignore[misc]

    def integrity_check(self, project_id: str) -> dict[str, Any]:
        return self._manifests.integrity_check(project_id)

    def close(self) -> None:
        self._conn.close()
