from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.nexus.config import NEXUS_PATHS
from app.nexus.utils import ensure_dir


REQUIRED_DIRS: tuple[Path, ...] = (
    NEXUS_PATHS.nexus_dir,
    NEXUS_PATHS.uploads_dir,
    NEXUS_PATHS.extracted_dir,
    NEXUS_PATHS.reports_dir,
    NEXUS_PATHS.exports_dir,
)


SCHEMA_SQL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS nexus_documents (
        id TEXT PRIMARY KEY,
        project TEXT NOT NULL,
        filename TEXT NOT NULL,
        size INTEGER NOT NULL,
        content_type TEXT NOT NULL,
        path TEXT NOT NULL,
        extracted_text_path TEXT NOT NULL DEFAULT '',
        markdown_path TEXT NOT NULL DEFAULT '',
        sha256 TEXT NOT NULL,
        metadata TEXT NOT NULL DEFAULT '{}',
        updated_at TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS nexus_chunks (
        chunk_id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL,
        chunk_index INTEGER NOT NULL,
        title TEXT NOT NULL,
        section_path TEXT NOT NULL,
        text TEXT NOT NULL,
        content TEXT NOT NULL,
        page_start INTEGER NOT NULL,
        page_end INTEGER NOT NULL,
        citation_label TEXT NOT NULL,
        metadata TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        FOREIGN KEY(document_id) REFERENCES nexus_documents(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS nexus_chunks_fts USING fts5(
        chunk_id UNINDEXED,
        title,
        section_path,
        text
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS nexus_jobs (
        job_id TEXT PRIMARY KEY,
        project TEXT NOT NULL DEFAULT 'default',
        job_type TEXT NOT NULL DEFAULT 'ingest',
        status TEXT NOT NULL,
        title TEXT,
        message TEXT,
        error TEXT,
        payload TEXT NOT NULL DEFAULT '{}',
        result TEXT NOT NULL DEFAULT '{}',
        document_count INTEGER NOT NULL DEFAULT 0,
        started_at TEXT,
        completed_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS nexus_job_events (
        job_id TEXT NOT NULL,
        seq INTEGER NOT NULL,
        type TEXT NOT NULL,
        data TEXT NOT NULL,
        ts TEXT NOT NULL,
        PRIMARY KEY(job_id, seq),
        FOREIGN KEY(job_id) REFERENCES nexus_jobs(job_id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS nexus_evidence (
        evidence_id TEXT PRIMARY KEY,
        project TEXT NOT NULL DEFAULT 'default',
        job_id TEXT NOT NULL,
        document_id TEXT NOT NULL DEFAULT '',
        chunk_id TEXT NOT NULL,
        title TEXT NOT NULL DEFAULT '',
        section_path TEXT NOT NULL DEFAULT '/',
        citation_label TEXT NOT NULL,
        source_url TEXT NOT NULL,
        retrieved_at TEXT NOT NULL,
        note TEXT,
        quote TEXT,
        metadata TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        FOREIGN KEY(job_id) REFERENCES nexus_jobs(job_id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS nexus_reports (
        report_id TEXT PRIMARY KEY,
        project TEXT NOT NULL DEFAULT 'default',
        job_id TEXT NOT NULL,
        report_type TEXT NOT NULL,
        title TEXT NOT NULL,
        report_dir TEXT NOT NULL,
        report_md_path TEXT NOT NULL,
        report_json_path TEXT NOT NULL,
        report_html_path TEXT NOT NULL,
        summary TEXT NOT NULL DEFAULT '',
        metadata TEXT NOT NULL DEFAULT '{}',
        generated_at TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(job_id) REFERENCES nexus_jobs(job_id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS nexus_watchlists (
        watchlist_id TEXT PRIMARY KEY,
        project TEXT NOT NULL,
        name TEXT NOT NULL,
        query TEXT NOT NULL,
        source_type TEXT NOT NULL DEFAULT 'news',
        is_active INTEGER NOT NULL DEFAULT 1,
        last_checked_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_evidence_job_id ON nexus_evidence(job_id)",
    "CREATE INDEX IF NOT EXISTS idx_reports_job_id ON nexus_reports(job_id)",
    "CREATE INDEX IF NOT EXISTS idx_reports_project ON nexus_reports(project)",
    "CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON nexus_chunks(document_id)",
    "CREATE INDEX IF NOT EXISTS idx_jobs_status ON nexus_jobs(status)",
    "CREATE INDEX IF NOT EXISTS idx_jobs_project ON nexus_jobs(project)",
    "CREATE INDEX IF NOT EXISTS idx_watchlists_project ON nexus_watchlists(project)",
)


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row[1]) for row in rows}


def _add_column_if_missing(conn: sqlite3.Connection, table: str, definition: str) -> None:
    name = definition.split()[0]
    if name not in _table_columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def _ensure_compat_migrations(conn: sqlite3.Connection) -> None:
    # ALTER TABLE 互換マイグレーション（既存データ保持）
    for table, definitions in (
        (
            "nexus_documents",
            (
                "metadata TEXT NOT NULL DEFAULT '{}'",
                "updated_at TEXT NOT NULL DEFAULT ''",
                "extracted_text_path TEXT NOT NULL DEFAULT ''",
                "markdown_path TEXT NOT NULL DEFAULT ''",
            ),
        ),
        (
            "nexus_chunks",
            (
                "text TEXT NOT NULL DEFAULT ''",
                "metadata TEXT NOT NULL DEFAULT '{}'",
            ),
        ),
        (
            "nexus_jobs",
            (
                "project TEXT NOT NULL DEFAULT 'default'",
                "job_type TEXT NOT NULL DEFAULT 'ingest'",
                "payload TEXT NOT NULL DEFAULT '{}'",
                "result TEXT NOT NULL DEFAULT '{}'",
                "started_at TEXT",
                "completed_at TEXT",
            ),
        ),
        (
            "nexus_evidence",
            (
                "project TEXT NOT NULL DEFAULT 'default'",
                "document_id TEXT NOT NULL DEFAULT ''",
                "title TEXT NOT NULL DEFAULT ''",
                "section_path TEXT NOT NULL DEFAULT '/'",
            ),
        ),
        (
            "nexus_reports",
            (
                "project TEXT NOT NULL DEFAULT 'default'",
                "summary TEXT NOT NULL DEFAULT ''",
                "metadata TEXT NOT NULL DEFAULT '{}'",
            ),
        ),
    ):
        for definition in definitions:
            _add_column_if_missing(conn, table, definition)

    # 欠損カラムのデフォルト埋め
    conn.execute("UPDATE nexus_documents SET metadata = '{}' WHERE metadata IS NULL OR metadata = ''")
    conn.execute("UPDATE nexus_documents SET updated_at = created_at WHERE updated_at IS NULL OR updated_at = ''")
    conn.execute("UPDATE nexus_documents SET extracted_text_path = '' WHERE extracted_text_path IS NULL")
    conn.execute("UPDATE nexus_documents SET markdown_path = '' WHERE markdown_path IS NULL")
    conn.execute("UPDATE nexus_chunks SET text = content WHERE text IS NULL OR text = ''")
    conn.execute("UPDATE nexus_chunks SET metadata = '{}' WHERE metadata IS NULL OR metadata = ''")
    conn.execute("UPDATE nexus_jobs SET project = 'default' WHERE project IS NULL OR project = ''")
    conn.execute("UPDATE nexus_jobs SET job_type = 'ingest' WHERE job_type IS NULL OR job_type = ''")
    conn.execute("UPDATE nexus_jobs SET payload = '{}' WHERE payload IS NULL OR payload = ''")
    conn.execute("UPDATE nexus_jobs SET result = '{}' WHERE result IS NULL OR result = ''")
    conn.execute("UPDATE nexus_jobs SET started_at = created_at WHERE started_at IS NULL")
    conn.execute(
        """
        UPDATE nexus_evidence
        SET project = 'default', document_id = '', title = '', section_path = '/'
        WHERE project IS NULL OR project = ''
           OR document_id IS NULL
           OR title IS NULL
           OR section_path IS NULL OR section_path = ''
        """
    )
    conn.execute("UPDATE nexus_reports SET project = 'default' WHERE project IS NULL OR project = ''")
    conn.execute("UPDATE nexus_reports SET summary = '' WHERE summary IS NULL")
    conn.execute("UPDATE nexus_reports SET metadata = '{}' WHERE metadata IS NULL OR metadata = ''")

    # FTS再構成（title/section_path/text を索引）
    conn.execute("DROP TABLE IF EXISTS nexus_chunks_fts")
    conn.execute(
        """
        CREATE VIRTUAL TABLE nexus_chunks_fts USING fts5(
            chunk_id UNINDEXED,
            title,
            section_path,
            text
        )
        """
    )
    conn.execute(
        """
        INSERT INTO nexus_chunks_fts(chunk_id, title, section_path, text)
        SELECT chunk_id, title, section_path, text
        FROM nexus_chunks
        """
    )


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys=ON;")
    for sql in SCHEMA_SQL:
        conn.execute(sql)
    _ensure_compat_migrations(conn)


def initialize_storage() -> Path:
    """`CA_DATA_DIR/nexus/nexus.db` と必要ディレクトリを初期化する。"""
    ensure_dir(NEXUS_PATHS.ca_data_dir)
    for directory in REQUIRED_DIRS:
        ensure_dir(directory)

    with sqlite3.connect(NEXUS_PATHS.db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        _ensure_schema(conn)
        conn.commit()

    return NEXUS_PATHS.db_path


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    """Nexus DB接続。"""
    initialize_storage()
    conn = sqlite3.connect(NEXUS_PATHS.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON;")
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    """Commit/rollback 付きトランザクション。"""
    with get_conn() as conn:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def insert_document(
    *,
    document_id: str,
    project: str,
    filename: str,
    size: int,
    content_type: str,
    path: str,
    sha256: str,
    created_at: str,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO nexus_documents(id, project, filename, size, content_type, path, sha256, created_at)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (document_id, project, filename, size, content_type, path, sha256, created_at),
        )
        conn.commit()


def update_document_artifact_paths(
    *,
    document_id: str,
    extracted_text_path: str,
    markdown_path: str,
    updated_at: str,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE nexus_documents
            SET extracted_text_path = ?, markdown_path = ?, updated_at = ?
            WHERE id = ?
            """,
            (extracted_text_path, markdown_path, updated_at, document_id),
        )
        conn.commit()


def insert_chunk(
    *,
    chunk_id: str,
    document_id: str,
    chunk_index: int,
    title: str,
    section_path: str,
    content: str,
    page_start: int,
    page_end: int,
    citation_label: str,
    created_at: str,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO nexus_chunks(
                chunk_id, document_id, chunk_index, title, section_path,
                text, content, page_start, page_end, citation_label, metadata, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chunk_id,
                document_id,
                chunk_index,
                title,
                section_path,
                content,
                content,
                page_start,
                page_end,
                citation_label,
                "{}",
                created_at,
            ),
        )
        conn.execute(
            "INSERT OR REPLACE INTO nexus_chunks_fts(chunk_id, title, section_path, text) VALUES(?, ?, ?, ?)",
            (chunk_id, title, section_path, content),
        )
        conn.commit()


DB_PATH = NEXUS_PATHS.db_path
NEXUS_DIR = NEXUS_PATHS.nexus_dir

# import時に初期化
initialize_storage()
