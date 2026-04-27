import sqlite3
import unittest

from app.nexus.db import SCHEMA_SQL, _ensure_compat_migrations


class NexusDbMigrationTests(unittest.TestCase):
    def test_rebuilds_legacy_nexus_sources_and_passes_foreign_key_check(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")

        for sql in SCHEMA_SQL:
            if "CREATE TABLE IF NOT EXISTS nexus_sources" in sql:
                continue
            if "idx_sources_" in sql:
                continue
            conn.execute(sql)

        conn.execute(
            """
            INSERT INTO nexus_documents(id, project, filename, size, content_type, path, sha256, created_at)
            VALUES('', 'default', 'placeholder.txt', 0, 'text/plain', '/tmp/placeholder.txt', 'hash', '2026-01-01T00:00:00+00:00')
            """
        )
        conn.execute(
            """
            CREATE TABLE nexus_sources (
                source_id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                project TEXT NOT NULL DEFAULT 'default',
                source_type TEXT NOT NULL DEFAULT '',
                url TEXT NOT NULL DEFAULT '',
                final_url TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                publisher TEXT NOT NULL DEFAULT '',
                domain TEXT NOT NULL DEFAULT '',
                language TEXT NOT NULL DEFAULT '',
                content_type TEXT NOT NULL DEFAULT '',
                local_original_path TEXT NOT NULL DEFAULT '',
                local_text_path TEXT NOT NULL DEFAULT '',
                local_markdown_path TEXT NOT NULL DEFAULT '',
                local_screenshot_path TEXT NOT NULL DEFAULT '',
                linked_document_id TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT '',
                source_score REAL NOT NULL DEFAULT 0.0,
                source_score_breakdown TEXT NOT NULL DEFAULT '{}',
                error TEXT NOT NULL DEFAULT '',
                retrieved_at TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(job_id) REFERENCES nexus_jobs(job_id) ON DELETE CASCADE,
                FOREIGN KEY(linked_document_id) REFERENCES nexus_documents(id) ON DELETE SET NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO nexus_jobs(job_id, status, created_at, updated_at)
            VALUES('job-1', 'running', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
            """
        )
        conn.execute(
            """
            INSERT INTO nexus_sources(
                source_id, job_id, project, source_type, url, final_url, title,
                publisher, domain, language, content_type,
                local_original_path, local_text_path, local_markdown_path, local_screenshot_path,
                linked_document_id, status, source_score, source_score_breakdown,
                error, retrieved_at, created_at, updated_at
            )
            VALUES(
                'src-1', 'job-1', 'default', '', '', '', '',
                '', '', '', '',
                '', '', '', '',
                '', '', 0.0, '{}',
                '', '', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
            )
            """
        )

        _ensure_compat_migrations(conn)

        linked_col = next(row for row in conn.execute("PRAGMA table_info(nexus_sources)") if row["name"] == "linked_document_id")
        self.assertEqual(linked_col["notnull"], 0)
        self.assertIn(linked_col["dflt_value"], (None, "NULL"))

        migrated_row = conn.execute("SELECT linked_document_id FROM nexus_sources WHERE source_id = 'src-1'").fetchone()
        self.assertIsNone(migrated_row["linked_document_id"])

        fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        self.assertEqual(fk_violations, [])

        conn.close()


if __name__ == "__main__":
    unittest.main()
