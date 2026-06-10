"""Shared, dependency-neutral SQLite persistence kernel for Project Intelligence (PI-2).

This module is an *internal* persistence adapter shared by the Blueprint, Convergence and
Project Intelligence module stores. It imports only stdlib (sqlite3/json/datetime); it must
NOT be imported by any portable *contract/facade* surface (ADR-PI-015: no consumer depends
on SQLite). The architecture-boundary test only scans contracts/facade/__init__, so this
adapter is allowed to use sqlite3.

It provides:
- a connection factory (foreign keys on, WAL on file DBs, explicit BEGIN/COMMIT);
- a transactional, repeatable, rollback-safe migration runner;
- a generic ``ArtifactStore`` of immutable, revisioned, project/workspace-isolated JSON
  artifacts with idempotency, stale-parent rejection, point-in-time reads, head pointers,
  and an integrity check with an explicit corruption signal.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


class StoreError(Exception):
    """Typed persistence error. Carries a stable code (mirrors IntelligenceErrorCode)."""

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        super().__init__(f"{code}: {message}" if message else code)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


SQLITE_MEMORY_PATH = ":" + "memory" + ":"


def default_sqlite_path(name: str) -> Path:
    """Return a file-backed default path for concrete stores."""
    root = Path(tempfile.gettempdir()) / "kasane_project_intelligence"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{name}-{uuid.uuid4().hex}.sqlite3"


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open an autocommit connection; callers control transactions with BEGIN/COMMIT."""
    path = str(db_path or default_sqlite_path("store"))
    conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if path not in (SQLITE_MEMORY_PATH, "") and not path.startswith("file::memory:"):
        try:
            conn.execute("PRAGMA journal_mode = WAL")
        except sqlite3.DatabaseError:  # pragma: no cover - platform dependent
            pass
    return conn


def _ensure_migration_table(conn: sqlite3.Connection, table: str) -> None:
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS {table} (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )


def current_schema_version(conn: sqlite3.Connection, migration_table: str) -> int:
    _ensure_migration_table(conn, migration_table)
    row = conn.execute(f"SELECT MAX(version) FROM {migration_table}").fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def apply_migrations(
    conn: sqlite3.Connection,
    migrations: list[tuple[int, list[str]]],
    *,
    migration_table: str,
    now_iso: str | None = None,
) -> int:
    """Apply pending migrations transactionally and idempotently.

    Each migration runs in its own transaction. A failing statement rolls the migration
    back, does not record its version, and re-raises — leaving the schema at the last
    good version. Re-running with no pending versions is a harmless no-op (repeatable).
    """
    now_iso = now_iso or _utcnow_iso()
    _ensure_migration_table(conn, migration_table)
    applied = current_schema_version(conn, migration_table)
    for version, statements in sorted(migrations, key=lambda m: m[0]):
        if version <= applied:
            continue
        try:
            conn.execute("BEGIN")
            for sql in statements:
                conn.execute(sql)
            conn.execute(
                f"INSERT INTO {migration_table} (version, applied_at) VALUES (?, ?)",
                (version, now_iso),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        applied = version
    return applied


def artifact_table_migration(table: str, *, version: int = 1) -> tuple[int, list[str]]:
    """Standard schema for one immutable revisioned-artifact table family.

    Creates ``<table>`` (immutable rows, unique per project+artifact), ``<table>_head``
    (current head per project+workspace+group) and ``<table>_idem`` (idempotency log).
    All statements use IF NOT EXISTS so migrations are repeatable.
    """
    return (
        version,
        [
            f"""
            CREATE TABLE IF NOT EXISTS {table} (
                row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                workspace_id TEXT NOT NULL,
                group_id TEXT NOT NULL,
                artifact_id TEXT NOT NULL,
                parent_artifact_id TEXT,
                artifact_type TEXT NOT NULL,
                status TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE (project_id, artifact_id)
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {table}_head (
                project_id TEXT NOT NULL,
                workspace_id TEXT NOT NULL,
                group_id TEXT NOT NULL,
                head_artifact_id TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (project_id, workspace_id, group_id)
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {table}_idem (
                project_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                artifact_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (project_id, idempotency_key)
            )
            """,
            f"CREATE INDEX IF NOT EXISTS idx_{table}_group ON {table} (project_id, group_id, created_at)",
        ],
    )


class ArtifactStore:
    """Generic immutable, revisioned, project/workspace-isolated artifact store.

    One ``put`` is exactly one transaction. Rows are never updated in place (immutable
    Blueprint/report history); only the head pointer moves. Reads are project-scoped, so
    no artifact leaks across project boundaries.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        table: str,
        *,
        now_fn: Callable[[], str] | None = None,
    ) -> None:
        self._conn = conn
        self._table = table
        self._now = now_fn or _utcnow_iso

    # -- writes ---------------------------------------------------------------

    def put(
        self,
        *,
        project_id: str,
        workspace_id: str,
        group_id: str,
        artifact_id: str,
        artifact_type: str,
        payload: dict[str, Any],
        status: str = "active",
        parent_artifact_id: str | None = None,
        expected_parent_id: str | None = None,
        idempotency_key: str | None = None,
        advance_head: bool = True,
    ) -> str:
        """Insert one immutable artifact atomically and (optionally) advance the head.

        - duplicate ``idempotency_key`` returns the prior artifact_id without writing;
        - ``expected_parent_id`` that does not match the current head is rejected as a
          stale revision (the parent is never edited);
        - reusing ``artifact_id`` with different content violates immutability and the
          whole transaction rolls back (no partial revision).
        """
        table = self._table
        # Idempotency is checked first so retries are harmless even if the head moved.
        if idempotency_key is not None:
            row = self._conn.execute(
                f"SELECT artifact_id FROM {table}_idem WHERE project_id = ? AND idempotency_key = ?",
                (project_id, idempotency_key),
            ).fetchone()
            if row is not None:
                return str(row["artifact_id"])

        if expected_parent_id is not None:
            current_head = self.get_head_id(project_id, workspace_id, group_id)
            if current_head != expected_parent_id:
                raise StoreError(
                    "stale_revision",
                    f"expected parent {expected_parent_id!r}, head is {current_head!r}",
                )

        payload_json = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
        now = self._now()
        try:
            self._conn.execute("BEGIN")
            self._conn.execute(
                f"""INSERT INTO {table}
                    (project_id, workspace_id, group_id, artifact_id, parent_artifact_id,
                     artifact_type, status, payload, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (project_id, workspace_id, group_id, artifact_id, parent_artifact_id,
                 artifact_type, status, payload_json, now),
            )
            if advance_head:
                self._conn.execute(
                    f"""INSERT INTO {table}_head
                        (project_id, workspace_id, group_id, head_artifact_id, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT (project_id, workspace_id, group_id)
                        DO UPDATE SET head_artifact_id = excluded.head_artifact_id,
                                      updated_at = excluded.updated_at""",
                    (project_id, workspace_id, group_id, artifact_id, now),
                )
            if idempotency_key is not None:
                self._conn.execute(
                    f"INSERT INTO {table}_idem (project_id, idempotency_key, artifact_id, created_at) VALUES (?, ?, ?, ?)",
                    (project_id, idempotency_key, artifact_id, now),
                )
            self._conn.execute("COMMIT")
        except sqlite3.IntegrityError as exc:
            self._conn.execute("ROLLBACK")
            raise StoreError("immutability_violation", str(exc)) from exc
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        return artifact_id

    def set_status(self, project_id: str, artifact_id: str, status: str) -> None:
        cur = self._conn.execute(
            f"UPDATE {self._table} SET status = ? WHERE project_id = ? AND artifact_id = ?",
            (status, project_id, artifact_id),
        )
        if cur.rowcount == 0:
            raise StoreError("revision_not_found", f"{artifact_id!r} not in project {project_id!r}")

    def list_heads(self, project_id: str, workspace_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            f"""SELECT a.* FROM {self._table}_head h
                JOIN {self._table} a
                  ON a.project_id = h.project_id
                 AND a.artifact_id = h.head_artifact_id
                WHERE h.project_id = ? AND h.workspace_id = ?
                ORDER BY h.group_id ASC""",
            (project_id, workspace_id),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    # -- reads (project-scoped) ----------------------------------------------

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "project_id": row["project_id"],
            "workspace_id": row["workspace_id"],
            "group_id": row["group_id"],
            "artifact_id": row["artifact_id"],
            "parent_artifact_id": row["parent_artifact_id"],
            "artifact_type": row["artifact_type"],
            "status": row["status"],
            "payload": json.loads(row["payload"]),
            "created_at": row["created_at"],
        }

    def get(self, project_id: str, artifact_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            f"SELECT * FROM {self._table} WHERE project_id = ? AND artifact_id = ?",
            (project_id, artifact_id),
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def get_head_id(self, project_id: str, workspace_id: str, group_id: str) -> str | None:
        row = self._conn.execute(
            f"SELECT head_artifact_id FROM {self._table}_head WHERE project_id = ? AND workspace_id = ? AND group_id = ?",
            (project_id, workspace_id, group_id),
        ).fetchone()
        return str(row["head_artifact_id"]) if row else None

    def get_head(self, project_id: str, workspace_id: str, group_id: str) -> dict[str, Any] | None:
        head_id = self.get_head_id(project_id, workspace_id, group_id)
        return self.get(project_id, head_id) if head_id else None

    def set_head(self, project_id: str, workspace_id: str, group_id: str, artifact_id: str) -> None:
        """Point the group head at an existing artifact (e.g. activate a revision).

        The target must already exist in the same project (no head ever dangles).
        """
        if self.get(project_id, artifact_id) is None:
            raise StoreError("revision_not_found", f"{artifact_id!r} not in project {project_id!r}")
        now = self._now()
        try:
            self._conn.execute("BEGIN")
            self._conn.execute(
                f"""INSERT INTO {self._table}_head
                    (project_id, workspace_id, group_id, head_artifact_id, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT (project_id, workspace_id, group_id)
                    DO UPDATE SET head_artifact_id = excluded.head_artifact_id,
                                  updated_at = excluded.updated_at""",
                (project_id, workspace_id, group_id, artifact_id, now),
            )
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    def list_history(self, project_id: str, group_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            f"SELECT * FROM {self._table} WHERE project_id = ? AND group_id = ? ORDER BY row_id ASC",
            (project_id, group_id),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def point_in_time(self, project_id: str, group_id: str, as_of_iso: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            f"""SELECT * FROM {self._table}
                WHERE project_id = ? AND group_id = ? AND created_at <= ?
                ORDER BY row_id DESC LIMIT 1""",
            (project_id, group_id, as_of_iso),
        ).fetchone()
        return self._row_to_dict(row) if row else None

    # -- integrity ------------------------------------------------------------

    def integrity_check(self, project_id: str) -> dict[str, Any]:
        """Verify head pointers and parent links resolve. Returns an explicit status."""
        diagnostics: list[str] = []
        heads = self._conn.execute(
            f"SELECT workspace_id, group_id, head_artifact_id FROM {self._table}_head WHERE project_id = ?",
            (project_id,),
        ).fetchall()
        for h in heads:
            if self.get(project_id, h["head_artifact_id"]) is None:
                diagnostics.append(f"dangling head {h['head_artifact_id']!r} for group {h['group_id']!r}")
        rows = self._conn.execute(
            f"SELECT artifact_id, parent_artifact_id FROM {self._table} WHERE project_id = ?",
            (project_id,),
        ).fetchall()
        for r in rows:
            parent = r["parent_artifact_id"]
            if parent and self.get(project_id, parent) is None:
                diagnostics.append(f"artifact {r['artifact_id']!r} has missing parent {parent!r}")
        return {"status": "ok" if not diagnostics else "corrupt", "diagnostics": diagnostics}
