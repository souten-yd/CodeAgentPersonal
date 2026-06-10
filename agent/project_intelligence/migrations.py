"""SQLite schema/migrations for the Project Intelligence store (PI-2).

Two families:
- ``pi_context_manifests``: immutable Context Manifest artifacts (revisioned, isolated);
- ``pi_jobs``: a restart-safe job journal with idempotent enqueue and status transitions
  (ADR-PI-011 outbox/journal semantics). Jobs are mutable (status moves queued -> running
  -> done/failed); manifests are immutable.

Repeatable and rollback-safe.
"""

from __future__ import annotations

from agent.project_intelligence._persistence import artifact_table_migration

MANIFEST_TABLE = "pi_context_manifests"
JOBS_TABLE = "pi_jobs"
MIGRATION_TABLE = "pi_schema_migrations"

SCHEMA_MIGRATIONS = [
    artifact_table_migration(MANIFEST_TABLE, version=1),
    (
        2,
        [
            f"""
            CREATE TABLE IF NOT EXISTS {JOBS_TABLE} (
                job_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                workspace_id TEXT NOT NULL,
                job_type TEXT NOT NULL,
                status TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                idempotency_key TEXT,
                payload TEXT NOT NULL DEFAULT '{{}}',
                last_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (project_id, job_id)
            )
            """,
            f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{JOBS_TABLE}_idem ON {JOBS_TABLE} (project_id, idempotency_key)",
            f"CREATE INDEX IF NOT EXISTS idx_{JOBS_TABLE}_status ON {JOBS_TABLE} (project_id, status, created_at)",
        ],
    ),
]
