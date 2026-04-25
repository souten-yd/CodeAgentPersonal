from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

_DB_LOCK = threading.Lock()


def _resolve_ca_data_dir() -> Path:
    base_dir = Path(__file__).resolve().parents[2]
    default_ca_data = base_dir / "ca_data"
    ca_data = Path(os.environ.get("CODEAGENT_CA_DATA_DIR", str(default_ca_data))).resolve()
    ca_data.mkdir(parents=True, exist_ok=True)
    return ca_data


CA_DATA_DIR = _resolve_ca_data_dir()
NEXUS_DIR = CA_DATA_DIR / "nexus"
DB_PATH = NEXUS_DIR / "nexus.db"

# NOTE:
# - DDL is centralized in a single script so the expected schema can be applied verbatim.
# - nexus_chunks_fts is implemented with FTS5 and synchronized in insert_chunk().
SCHEMA_DDL = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS nexus_documents (
    id TEXT PRIMARY KEY,
    project TEXT NOT NULL,
    filename TEXT NOT NULL,
    size INTEGER NOT NULL,
    content_type TEXT NOT NULL,
    path TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS nexus_chunks (
    chunk_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(document_id) REFERENCES nexus_documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS nexus_jobs (
    job_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    title TEXT,
    message TEXT,
    document_count INTEGER NOT NULL DEFAULT 0,
    download_url TEXT,
    bundle_path TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS nexus_job_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES nexus_jobs(job_id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_nexus_job_events_job_seq
    ON nexus_job_events(job_id, seq);
CREATE INDEX IF NOT EXISTS idx_nexus_jobs_status_updated
    ON nexus_jobs(status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_nexus_chunks_document
    ON nexus_chunks(document_id, chunk_index);

CREATE VIRTUAL TABLE IF NOT EXISTS nexus_chunks_fts USING fts5(
    chunk_id UNINDEXED,
    document_id UNINDEXED,
    content,
    tokenize='unicode61'
);
"""


def initialize_db() -> Path:
    NEXUS_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
        conn.executescript(SCHEMA_DDL)
        conn.commit()
    return DB_PATH


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    initialize_db()
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    with _DB_LOCK:
        with get_conn() as conn:
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise


def insert_chunk(chunk_id: str, document_id: str, chunk_index: int, content: str, created_at: str) -> None:
    """Insert chunk and keep FTS index in sync."""
    with transaction() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO nexus_chunks (chunk_id, document_id, chunk_index, content, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (chunk_id, document_id, chunk_index, content, created_at),
        )
        conn.execute("DELETE FROM nexus_chunks_fts WHERE chunk_id = ?", (chunk_id,))
        conn.execute(
            """
            INSERT INTO nexus_chunks_fts (chunk_id, document_id, content)
            VALUES (?, ?, ?)
            """,
            (chunk_id, document_id, content),
        )


# Ensure DB exists at import time.
initialize_db()
