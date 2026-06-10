"""SQLite schema/migrations for the Convergence store (PI-2).

Immutable Convergence report history grouped by ``blueprint_revision_id``. Reports are
never mutated; the latest report per group is the head. Repeatable and rollback-safe.
"""

from __future__ import annotations

from agent.project_intelligence._persistence import artifact_table_migration

CONVERGENCE_TABLE = "convergence_reports"
MIGRATION_TABLE = "convergence_schema_migrations"

SCHEMA_MIGRATIONS = [artifact_table_migration(CONVERGENCE_TABLE)]
