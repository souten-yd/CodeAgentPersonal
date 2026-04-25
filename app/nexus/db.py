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
        sha256 TEXT NOT NULL,
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
        content TEXT NOT NULL,
        page_start INTEGER NOT NULL,
        page_end INTEGER NOT NULL,
        citation_label TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(document_id) REFERENCES nexus_documents(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS nexus_chunks_fts USING fts5(
        chunk_id UNINDEXED,
        content
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS nexus_jobs (
        job_id TEXT PRIMARY KEY,
        status TEXT NOT NULL,
        title TEXT,
        message TEXT,
        error TEXT,
        document_count INTEGER NOT NULL DEFAULT 0,
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
        job_id TEXT NOT NULL,
        chunk_id TEXT NOT NULL,
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
        job_id TEXT NOT NULL,
        report_type TEXT NOT NULL,
        title TEXT NOT NULL,
        report_dir TEXT NOT NULL,
        report_md_path TEXT NOT NULL,
        report_json_path TEXT NOT NULL,
        report_html_path TEXT NOT NULL,
        generated_at TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(job_id) REFERENCES nexus_jobs(job_id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_evidence_job_id ON nexus_evidence(job_id)",
    "CREATE INDEX IF NOT EXISTS idx_reports_job_id ON nexus_reports(job_id)",
    "CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON nexus_chunks(document_id)",
    "CREATE INDEX IF NOT EXISTS idx_jobs_status ON nexus_jobs(status)",
)


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys=ON;")
    for sql in SCHEMA_SQL:
        conn.execute(sql)


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
                content, page_start, page_end, citation_label, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chunk_id,
                document_id,
                chunk_index,
                title,
                section_path,
                content,
                page_start,
                page_end,
                citation_label,
                created_at,
            ),
        )
        conn.execute(
            "INSERT OR REPLACE INTO nexus_chunks_fts(chunk_id, content) VALUES(?, ?)",
            (chunk_id, content),
        )
        conn.commit()


DB_PATH = NEXUS_PATHS.db_path
NEXUS_DIR = NEXUS_PATHS.nexus_dir

# import時に初期化
initialize_storage()
