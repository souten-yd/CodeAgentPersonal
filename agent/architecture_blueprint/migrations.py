"""SQLite schema/migrations for the Architecture Blueprint store (PI-2).

Immutable Blueprint revision rows grouped by ``blueprint_id``. Repeatable and
rollback-safe (see ``agent.project_intelligence._persistence.apply_migrations``).
"""

from __future__ import annotations

from agent.project_intelligence._persistence import artifact_table_migration

BLUEPRINT_TABLE = "blueprint_revisions"
MIGRATION_TABLE = "blueprint_schema_migrations"

SCHEMA_MIGRATIONS = [artifact_table_migration(BLUEPRINT_TABLE)]
