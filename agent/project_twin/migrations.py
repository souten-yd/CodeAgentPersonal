"""SQLite schema and migration runner for the Twin Store (PDT-2).

The storage contract (`docs/atlas_project_digital_twin_contracts.md` section 8) requires
these tables, foreign keys enabled, WAL where supported, project-scoped indexes and an
idempotency unique key. Migrations are explicit, versioned and applied transactionally:
a failing migration rolls back and is not recorded.
"""

from __future__ import annotations

import sqlite3

# Each migration is (version, list-of-SQL-statements). Versions apply in ascending order.
SCHEMA_MIGRATIONS: list[tuple[int, list[str]]] = [
    (
        1,
        [
            """
            CREATE TABLE IF NOT EXISTS twin_projects (
                project_id TEXT PRIMARY KEY,
                contract_version TEXT NOT NULL,
                head_revision_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS twin_revisions (
                revision_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                parent_revision_id TEXT,
                source_commit TEXT,
                working_tree_hash TEXT,
                trigger_type TEXT NOT NULL,
                trigger_ref TEXT,
                parser_versions TEXT NOT NULL DEFAULT '{}',
                node_upserts INTEGER NOT NULL DEFAULT 0,
                edge_upserts INTEGER NOT NULL DEFAULT 0,
                invalidations INTEGER NOT NULL DEFAULT 0,
                observations_added INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES twin_projects (project_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS twin_nodes (
                row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                domain TEXT NOT NULL,
                node_type TEXT NOT NULL,
                canonical_ref TEXT NOT NULL,
                label TEXT NOT NULL,
                properties TEXT NOT NULL DEFAULT '{}',
                source_kind TEXT NOT NULL,
                source_ref TEXT NOT NULL,
                source_revision TEXT,
                content_revision TEXT,
                derivation TEXT NOT NULL,
                confidence REAL NOT NULL,
                status TEXT NOT NULL,
                evidence_refs TEXT NOT NULL DEFAULT '[]',
                observed_at TEXT,
                valid_from TEXT NOT NULL,
                valid_to TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                revision_id TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES twin_projects (project_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS twin_edges (
                row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                edge_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                domain TEXT NOT NULL,
                source_node_id TEXT NOT NULL,
                target_node_id TEXT NOT NULL,
                edge_type TEXT NOT NULL,
                properties TEXT NOT NULL DEFAULT '{}',
                source_kind TEXT NOT NULL,
                source_ref TEXT NOT NULL,
                source_revision TEXT,
                derivation TEXT NOT NULL,
                confidence REAL NOT NULL,
                status TEXT NOT NULL,
                evidence_refs TEXT NOT NULL DEFAULT '[]',
                valid_from TEXT NOT NULL,
                valid_to TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                revision_id TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES twin_projects (project_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS twin_evidence (
                row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                evidence_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                evidence_type TEXT NOT NULL,
                source_kind TEXT NOT NULL,
                source_ref TEXT NOT NULL,
                source_revision TEXT,
                summary TEXT NOT NULL,
                payload_ref TEXT,
                content_hash TEXT,
                confidence REAL NOT NULL,
                observed_at TEXT,
                created_at TEXT NOT NULL,
                revision_id TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES twin_projects (project_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS twin_observations (
                row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                observation_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                run_id TEXT,
                collector TEXT NOT NULL,
                collector_version TEXT NOT NULL,
                observation_type TEXT NOT NULL,
                subject_refs TEXT NOT NULL DEFAULT '[]',
                timestamp TEXT NOT NULL,
                result TEXT NOT NULL,
                summary TEXT NOT NULL,
                payload_ref TEXT,
                evidence_ids TEXT NOT NULL DEFAULT '[]',
                revision_id TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES twin_projects (project_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS twin_delta_log (
                project_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                revision_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (project_id, idempotency_key)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS twin_projection_jobs (
                job_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                job_type TEXT NOT NULL,
                status TEXT NOT NULL,
                detail TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_twin_nodes_current ON twin_nodes (project_id, canonical_ref, valid_to)",
            "CREATE INDEX IF NOT EXISTS idx_twin_nodes_type ON twin_nodes (project_id, node_type, valid_to)",
            "CREATE INDEX IF NOT EXISTS idx_twin_nodes_nodeid ON twin_nodes (project_id, node_id, valid_to)",
            "CREATE INDEX IF NOT EXISTS idx_twin_edges_current ON twin_edges (project_id, edge_type, source_node_id, target_node_id, valid_to)",
            "CREATE INDEX IF NOT EXISTS idx_twin_edges_endpoints ON twin_edges (project_id, source_node_id, valid_to)",
            "CREATE INDEX IF NOT EXISTS idx_twin_revisions_project ON twin_revisions (project_id, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_twin_evidence_project ON twin_evidence (project_id)",
            "CREATE INDEX IF NOT EXISTS idx_twin_observations_project ON twin_observations (project_id)",
        ],
    ),
]


def _ensure_migration_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS twin_schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )


def current_schema_version(conn: sqlite3.Connection) -> int:
    _ensure_migration_table(conn)
    row = conn.execute("SELECT MAX(version) FROM twin_schema_migrations").fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def apply_migrations(
    conn: sqlite3.Connection,
    migrations: list[tuple[int, list[str]]] | None = None,
    *,
    now_iso: str,
) -> int:
    """Apply pending migrations transactionally.

    Each migration runs inside its own transaction. If any statement fails, that
    migration is rolled back, its version is not recorded, and the error propagates,
    leaving the schema at the last successfully applied version.
    """

    migrations = SCHEMA_MIGRATIONS if migrations is None else migrations
    _ensure_migration_table(conn)
    applied = current_schema_version(conn)
    for version, statements in sorted(migrations, key=lambda m: m[0]):
        if version <= applied:
            continue
        try:
            conn.execute("BEGIN")
            for sql in statements:
                conn.execute(sql)
            conn.execute(
                "INSERT INTO twin_schema_migrations (version, applied_at) VALUES (?, ?)",
                (version, now_iso),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        applied = version
    return applied
