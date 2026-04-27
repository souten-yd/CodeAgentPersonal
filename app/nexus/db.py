from __future__ import annotations

import json
import sqlite3
import threading
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
        source_metadata TEXT NOT NULL DEFAULT '{}',
        doc_metadata TEXT NOT NULL DEFAULT '{}',
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
        document_id UNINDEXED,
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
        progress REAL NOT NULL DEFAULT 0.0,
        input_json TEXT NOT NULL DEFAULT '{}',
        output_json TEXT NOT NULL DEFAULT '{}',
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
        source_id TEXT NOT NULL DEFAULT '',
        source_type TEXT NOT NULL DEFAULT '',
        document_id TEXT NOT NULL DEFAULT '',
        chunk_id TEXT NOT NULL,
        title TEXT NOT NULL DEFAULT '',
        publisher TEXT NOT NULL DEFAULT '',
        published_date TEXT NOT NULL DEFAULT '',
        section_path TEXT NOT NULL DEFAULT '/',
        citation_label TEXT NOT NULL,
        source_url TEXT NOT NULL,
        retrieved_at TEXT NOT NULL,
        note TEXT,
        quote TEXT,
        relevance REAL NOT NULL DEFAULT 0.0,
        credibility REAL NOT NULL DEFAULT 0.0,
        freshness REAL NOT NULL DEFAULT 0.0,
        evidence_level TEXT NOT NULL DEFAULT '',
        metadata_json TEXT NOT NULL DEFAULT '{}',
        metadata TEXT NOT NULL DEFAULT '{}',
        url TEXT NOT NULL DEFAULT '',
        relevance_score REAL NOT NULL DEFAULT 0.0,
        credibility_score REAL NOT NULL DEFAULT 0.0,
        freshness_score REAL NOT NULL DEFAULT 0.0,
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
        markdown_path TEXT NOT NULL DEFAULT '',
        json_path TEXT NOT NULL DEFAULT '',
        html_path TEXT NOT NULL DEFAULT '',
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
    """
    CREATE TABLE IF NOT EXISTS nexus_sources (
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
    """,
    """
    CREATE TABLE IF NOT EXISTS nexus_research_answers (
        answer_id TEXT PRIMARY KEY,
        job_id TEXT NOT NULL,
        project TEXT NOT NULL DEFAULT 'default',
        question TEXT NOT NULL DEFAULT '',
        answer_markdown TEXT NOT NULL DEFAULT '',
        evidence_json TEXT NOT NULL DEFAULT '[]',
        answer_json TEXT NOT NULL DEFAULT '{}',
        source_ids_json TEXT NOT NULL DEFAULT '[]',
        created_at TEXT NOT NULL,
        FOREIGN KEY(job_id) REFERENCES nexus_jobs(job_id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS nexus_source_chunks (
        id TEXT PRIMARY KEY,
        source_id TEXT NOT NULL,
        document_id TEXT NOT NULL DEFAULT '',
        chunk_id TEXT NOT NULL DEFAULT '',
        page_start INTEGER NOT NULL DEFAULT 0,
        page_end INTEGER NOT NULL DEFAULT 0,
        section_path TEXT NOT NULL DEFAULT '',
        citation_label TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        FOREIGN KEY(source_id) REFERENCES nexus_sources(source_id) ON DELETE CASCADE,
        FOREIGN KEY(document_id) REFERENCES nexus_documents(id) ON DELETE CASCADE,
        FOREIGN KEY(chunk_id) REFERENCES nexus_chunks(chunk_id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_evidence_job_id ON nexus_evidence(job_id)",
    "CREATE INDEX IF NOT EXISTS idx_reports_job_id ON nexus_reports(job_id)",
    "CREATE INDEX IF NOT EXISTS idx_reports_project ON nexus_reports(project)",
    "CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON nexus_chunks(document_id)",
    "CREATE INDEX IF NOT EXISTS idx_jobs_status ON nexus_jobs(status)",
    "CREATE INDEX IF NOT EXISTS idx_jobs_project ON nexus_jobs(project)",
    "CREATE INDEX IF NOT EXISTS idx_watchlists_project ON nexus_watchlists(project)",
    "CREATE INDEX IF NOT EXISTS idx_sources_job_id ON nexus_sources(job_id)",
    "CREATE INDEX IF NOT EXISTS idx_sources_linked_document_id ON nexus_sources(linked_document_id)",
    "CREATE INDEX IF NOT EXISTS idx_research_answers_job_id ON nexus_research_answers(job_id)",
    "CREATE INDEX IF NOT EXISTS idx_source_chunks_source_id ON nexus_source_chunks(source_id)",
    "CREATE INDEX IF NOT EXISTS idx_source_chunks_chunk_id ON nexus_source_chunks(chunk_id)",
)


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row[1]) for row in rows}


def _add_column_if_missing(conn: sqlite3.Connection, table: str, definition: str) -> None:
    name = definition.split()[0]
    if name not in _table_columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def _loads_json(value: object) -> dict:
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _dumps_json(value: object) -> str:
    if not isinstance(value, dict):
        return "{}"
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _ensure_compat_migrations(conn: sqlite3.Connection) -> None:
    # ALTER TABLE 互換マイグレーション（既存データ保持）
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS nexus_sources (
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
        CREATE TABLE IF NOT EXISTS nexus_research_answers (
            answer_id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            project TEXT NOT NULL DEFAULT 'default',
            question TEXT NOT NULL DEFAULT '',
            answer_markdown TEXT NOT NULL DEFAULT '',
            evidence_json TEXT NOT NULL DEFAULT '[]',
            answer_json TEXT NOT NULL DEFAULT '{}',
            source_ids_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            FOREIGN KEY(job_id) REFERENCES nexus_jobs(job_id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS nexus_source_chunks (
            id TEXT PRIMARY KEY,
            source_id TEXT NOT NULL,
            document_id TEXT NOT NULL DEFAULT '',
            chunk_id TEXT NOT NULL DEFAULT '',
            page_start INTEGER NOT NULL DEFAULT 0,
            page_end INTEGER NOT NULL DEFAULT 0,
            section_path TEXT NOT NULL DEFAULT '',
            citation_label TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY(source_id) REFERENCES nexus_sources(source_id) ON DELETE CASCADE,
            FOREIGN KEY(document_id) REFERENCES nexus_documents(id) ON DELETE CASCADE,
            FOREIGN KEY(chunk_id) REFERENCES nexus_chunks(chunk_id) ON DELETE CASCADE
        )
        """
    )

    for table, definitions in (
        (
            "nexus_documents",
            (
                "metadata TEXT NOT NULL DEFAULT '{}'",
                "source_metadata TEXT NOT NULL DEFAULT '{}'",
                "doc_metadata TEXT NOT NULL DEFAULT '{}'",
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
                "error TEXT",
                "progress REAL NOT NULL DEFAULT 0.0",
                "input_json TEXT NOT NULL DEFAULT '{}'",
                "output_json TEXT NOT NULL DEFAULT '{}'",
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
                "source_id TEXT NOT NULL DEFAULT ''",
                "document_id TEXT NOT NULL DEFAULT ''",
                "title TEXT NOT NULL DEFAULT ''",
                "source_type TEXT NOT NULL DEFAULT ''",
                "publisher TEXT NOT NULL DEFAULT ''",
                "published_date TEXT NOT NULL DEFAULT ''",
                "section_path TEXT NOT NULL DEFAULT '/'",
                "relevance REAL NOT NULL DEFAULT 0.0",
                "credibility REAL NOT NULL DEFAULT 0.0",
                "freshness REAL NOT NULL DEFAULT 0.0",
                "evidence_level TEXT NOT NULL DEFAULT ''",
                "metadata_json TEXT NOT NULL DEFAULT '{}'",
                "url TEXT NOT NULL DEFAULT ''",
                "relevance_score REAL NOT NULL DEFAULT 0.0",
                "credibility_score REAL NOT NULL DEFAULT 0.0",
                "freshness_score REAL NOT NULL DEFAULT 0.0",
            ),
        ),
        (
            "nexus_reports",
            (
                "project TEXT NOT NULL DEFAULT 'default'",
                "summary TEXT NOT NULL DEFAULT ''",
                "metadata TEXT NOT NULL DEFAULT '{}'",
                "markdown_path TEXT NOT NULL DEFAULT ''",
                "json_path TEXT NOT NULL DEFAULT ''",
                "html_path TEXT NOT NULL DEFAULT ''",
            ),
        ),
        (
            "nexus_sources",
            (
                "job_id TEXT NOT NULL DEFAULT ''",
                "project TEXT NOT NULL DEFAULT 'default'",
                "source_type TEXT NOT NULL DEFAULT ''",
                "url TEXT NOT NULL DEFAULT ''",
                "final_url TEXT NOT NULL DEFAULT ''",
                "title TEXT NOT NULL DEFAULT ''",
                "publisher TEXT NOT NULL DEFAULT ''",
                "domain TEXT NOT NULL DEFAULT ''",
                "language TEXT NOT NULL DEFAULT ''",
                "content_type TEXT NOT NULL DEFAULT ''",
                "local_original_path TEXT NOT NULL DEFAULT ''",
                "local_text_path TEXT NOT NULL DEFAULT ''",
                "local_markdown_path TEXT NOT NULL DEFAULT ''",
                "local_screenshot_path TEXT NOT NULL DEFAULT ''",
                "linked_document_id TEXT NOT NULL DEFAULT ''",
                "status TEXT NOT NULL DEFAULT ''",
                "source_score REAL NOT NULL DEFAULT 0.0",
                "source_score_breakdown TEXT NOT NULL DEFAULT '{}'",
                "error TEXT NOT NULL DEFAULT ''",
                "retrieved_at TEXT NOT NULL DEFAULT ''",
                "created_at TEXT NOT NULL DEFAULT ''",
                "updated_at TEXT NOT NULL DEFAULT ''",
            ),
        ),
        (
            "nexus_research_answers",
            (
                "job_id TEXT NOT NULL DEFAULT ''",
                "project TEXT NOT NULL DEFAULT 'default'",
                "question TEXT NOT NULL DEFAULT ''",
                "answer_markdown TEXT NOT NULL DEFAULT ''",
                "evidence_json TEXT NOT NULL DEFAULT '[]'",
                "answer_json TEXT NOT NULL DEFAULT '{}'",
                "source_ids_json TEXT NOT NULL DEFAULT '[]'",
                "created_at TEXT NOT NULL DEFAULT ''",
            ),
        ),
        (
            "nexus_source_chunks",
            (
                "source_id TEXT NOT NULL DEFAULT ''",
                "document_id TEXT NOT NULL DEFAULT ''",
                "chunk_id TEXT NOT NULL DEFAULT ''",
                "page_start INTEGER NOT NULL DEFAULT 0",
                "page_end INTEGER NOT NULL DEFAULT 0",
                "section_path TEXT NOT NULL DEFAULT ''",
                "citation_label TEXT NOT NULL DEFAULT ''",
                "created_at TEXT NOT NULL DEFAULT ''",
            ),
        ),
    ):
        for definition in definitions:
            _add_column_if_missing(conn, table, definition)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_sources_job_id ON nexus_sources(job_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sources_linked_document_id ON nexus_sources(linked_document_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_research_answers_job_id ON nexus_research_answers(job_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_source_chunks_source_id ON nexus_source_chunks(source_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_source_chunks_chunk_id ON nexus_source_chunks(chunk_id)")

    # 欠損カラムのデフォルト埋め
    conn.execute("UPDATE nexus_documents SET metadata = '{}' WHERE metadata IS NULL OR metadata = ''")
    conn.execute("UPDATE nexus_documents SET source_metadata = '{}' WHERE source_metadata IS NULL OR source_metadata = ''")
    conn.execute("UPDATE nexus_documents SET doc_metadata = '{}' WHERE doc_metadata IS NULL OR doc_metadata = ''")
    conn.execute("UPDATE nexus_documents SET updated_at = created_at WHERE updated_at IS NULL OR updated_at = ''")
    conn.execute("UPDATE nexus_documents SET extracted_text_path = '' WHERE extracted_text_path IS NULL")
    conn.execute("UPDATE nexus_documents SET markdown_path = '' WHERE markdown_path IS NULL")
    conn.execute("UPDATE nexus_chunks SET text = content WHERE text IS NULL OR text = ''")
    conn.execute("UPDATE nexus_chunks SET metadata = '{}' WHERE metadata IS NULL OR metadata = ''")
    conn.execute("UPDATE nexus_jobs SET project = 'default' WHERE project IS NULL OR project = ''")
    conn.execute("UPDATE nexus_jobs SET job_type = 'ingest' WHERE job_type IS NULL OR job_type = ''")
    conn.execute("UPDATE nexus_jobs SET progress = 0.0 WHERE progress IS NULL")
    conn.execute("UPDATE nexus_jobs SET input_json = '{}' WHERE input_json IS NULL OR input_json = ''")
    conn.execute("UPDATE nexus_jobs SET output_json = '{}' WHERE output_json IS NULL OR output_json = ''")
    conn.execute("UPDATE nexus_jobs SET error = '' WHERE error IS NULL")
    conn.execute("UPDATE nexus_jobs SET payload = '{}' WHERE payload IS NULL OR payload = ''")
    conn.execute("UPDATE nexus_jobs SET result = '{}' WHERE result IS NULL OR result = ''")
    conn.execute("UPDATE nexus_jobs SET started_at = created_at WHERE started_at IS NULL")
    conn.execute(
        """
        UPDATE nexus_evidence
        SET project = 'default', source_id = '', source_type = '', document_id = '', title = '',
            publisher = '', published_date = '', section_path = '/'
        WHERE project IS NULL OR project = ''
           OR source_id IS NULL
           OR source_type IS NULL
           OR document_id IS NULL
           OR title IS NULL
           OR publisher IS NULL
           OR published_date IS NULL
           OR section_path IS NULL OR section_path = ''
        """
    )
    conn.execute("UPDATE nexus_evidence SET relevance = 0.0 WHERE relevance IS NULL")
    conn.execute("UPDATE nexus_evidence SET credibility = 0.0 WHERE credibility IS NULL")
    conn.execute("UPDATE nexus_evidence SET freshness = 0.0 WHERE freshness IS NULL")
    conn.execute("UPDATE nexus_evidence SET evidence_level = '' WHERE evidence_level IS NULL")
    conn.execute("UPDATE nexus_evidence SET metadata_json = '{}' WHERE metadata_json IS NULL OR metadata_json = ''")
    conn.execute("UPDATE nexus_evidence SET url = source_url WHERE url IS NULL OR url = ''")
    conn.execute("UPDATE nexus_evidence SET source_url = url WHERE source_url IS NULL OR source_url = ''")
    conn.execute("UPDATE nexus_evidence SET relevance_score = relevance WHERE relevance_score IS NULL")
    conn.execute("UPDATE nexus_evidence SET credibility_score = credibility WHERE credibility_score IS NULL")
    conn.execute("UPDATE nexus_evidence SET freshness_score = freshness WHERE freshness_score IS NULL")
    conn.execute("UPDATE nexus_evidence SET relevance = relevance_score WHERE relevance IS NULL")
    conn.execute("UPDATE nexus_evidence SET credibility = credibility_score WHERE credibility IS NULL")
    conn.execute("UPDATE nexus_sources SET source_score = 0.0 WHERE source_score IS NULL")
    conn.execute(
        "UPDATE nexus_sources SET source_score_breakdown = '{}' WHERE source_score_breakdown IS NULL OR source_score_breakdown = ''"
    )
    conn.execute("UPDATE nexus_evidence SET freshness = freshness_score WHERE freshness IS NULL")
    conn.execute("UPDATE nexus_research_answers SET answer_json = '{}' WHERE answer_json IS NULL OR answer_json = ''")
    conn.execute(
        """
        UPDATE nexus_evidence
        SET source_id = COALESCE(NULLIF(json_extract(metadata_json, '$.source_id'), ''), '')
        WHERE source_id = ''
          AND COALESCE(NULLIF(json_extract(metadata_json, '$.source_id'), ''), '') != ''
        """
    )
    conn.execute("UPDATE nexus_reports SET project = 'default' WHERE project IS NULL OR project = ''")
    conn.execute("UPDATE nexus_reports SET summary = '' WHERE summary IS NULL")
    conn.execute("UPDATE nexus_reports SET metadata = '{}' WHERE metadata IS NULL OR metadata = ''")
    conn.execute("UPDATE nexus_reports SET markdown_path = report_md_path WHERE markdown_path IS NULL OR markdown_path = ''")
    conn.execute("UPDATE nexus_reports SET json_path = report_json_path WHERE json_path IS NULL OR json_path = ''")
    conn.execute("UPDATE nexus_reports SET html_path = report_html_path WHERE html_path IS NULL OR html_path = ''")
    conn.execute("UPDATE nexus_reports SET report_md_path = markdown_path WHERE report_md_path IS NULL OR report_md_path = ''")
    conn.execute("UPDATE nexus_reports SET report_json_path = json_path WHERE report_json_path IS NULL OR report_json_path = ''")
    conn.execute("UPDATE nexus_reports SET report_html_path = html_path WHERE report_html_path IS NULL OR report_html_path = ''")

    # 旧 metadata JSON から新カラムへ補完
    doc_rows = conn.execute(
        "SELECT id, metadata, source_metadata, doc_metadata FROM nexus_documents"
    ).fetchall()
    for row in doc_rows:
        metadata = _loads_json(row["metadata"])
        source_metadata = _loads_json(row["source_metadata"])
        doc_metadata = _loads_json(row["doc_metadata"])
        if not source_metadata:
            source_candidate = metadata.get("source")
            if isinstance(source_candidate, dict):
                source_metadata = source_candidate
        if not doc_metadata:
            doc_candidate = metadata.get("document") or metadata.get("doc")
            if isinstance(doc_candidate, dict):
                doc_metadata = doc_candidate
        conn.execute(
            """
            UPDATE nexus_documents
            SET source_metadata = ?, doc_metadata = ?
            WHERE id = ?
            """,
            (_dumps_json(source_metadata), _dumps_json(doc_metadata), row["id"]),
        )

    job_rows = conn.execute(
        "SELECT job_id, payload, result, input_json, output_json FROM nexus_jobs"
    ).fetchall()
    for row in job_rows:
        payload = _loads_json(row["payload"])
        result = _loads_json(row["result"])
        input_json = _loads_json(row["input_json"]) or payload
        output_json = _loads_json(row["output_json"]) or result
        conn.execute(
            """
            UPDATE nexus_jobs
            SET input_json = ?, output_json = ?
            WHERE job_id = ?
            """,
            (_dumps_json(input_json), _dumps_json(output_json), row["job_id"]),
        )

    evidence_rows = conn.execute(
        """
        SELECT evidence_id, source_id, source_type, publisher, published_date, metadata_json,
               metadata, source_url, url, relevance, credibility, freshness,
               relevance_score, credibility_score, freshness_score, evidence_level
        FROM nexus_evidence
        """
    ).fetchall()
    for row in evidence_rows:
        metadata_json = _loads_json(row["metadata_json"])
        metadata = _loads_json(row["metadata"])
        if not metadata_json:
            metadata_json = metadata
        source_id = row["source_id"] if row["source_id"] not in (None, "") else metadata_json.get("source_id", "")
        source_type = row["source_type"] if row["source_type"] not in (None, "") else metadata_json.get("source_type", metadata_json.get("source", ""))
        publisher = row["publisher"] if row["publisher"] not in (None, "") else metadata_json.get("publisher", "")
        published_date = row["published_date"] if row["published_date"] not in (None, "") else metadata_json.get("published_date", metadata_json.get("published_at", ""))
        url = row["url"] if row["url"] not in (None, "") else row["source_url"]
        relevance = row["relevance_score"] if row["relevance_score"] not in (None, 0, 0.0) else row["relevance"]
        if relevance in (None, 0, 0.0):
            relevance = metadata_json.get("relevance_score", metadata_json.get("relevance", metadata_json.get("score", 0.0)))
        credibility = row["credibility_score"] if row["credibility_score"] not in (None, 0, 0.0) else row["credibility"]
        if credibility in (None, 0, 0.0):
            credibility = metadata_json.get("credibility_score", metadata_json.get("credibility", 0.0))
        freshness = row["freshness_score"] if row["freshness_score"] not in (None, 0, 0.0) else row["freshness"]
        if freshness in (None, 0, 0.0):
            freshness = metadata_json.get("freshness_score", metadata_json.get("freshness", 0.0))
        evidence_level = row["evidence_level"] if row["evidence_level"] not in (None, "") else metadata_json.get("evidence_level", metadata_json.get("level", ""))
        conn.execute(
            """
            UPDATE nexus_evidence
            SET source_id = ?, source_type = ?, publisher = ?, published_date = ?,
                source_url = ?, url = ?,
                relevance = ?, relevance_score = ?,
                credibility = ?, credibility_score = ?,
                freshness = ?, freshness_score = ?,
                evidence_level = ?,
                metadata_json = ?, metadata = ?
            WHERE evidence_id = ?
            """,
            (
                str(source_id or ""),
                str(source_type or ""),
                str(publisher or ""),
                str(published_date or ""),
                str(url or ""),
                str(url or ""),
                float(relevance or 0.0),
                float(relevance or 0.0),
                float(credibility or 0.0),
                float(credibility or 0.0),
                float(freshness or 0.0),
                float(freshness or 0.0),
                str(evidence_level or ""),
                _dumps_json(metadata_json),
                _dumps_json(metadata_json),
                row["evidence_id"],
            ),
        )

def rebuild_chunks_fts() -> None:
    with _connect_db() as conn:
        conn.execute("DROP TABLE IF EXISTS nexus_chunks_fts")
        conn.execute(
            """
            CREATE VIRTUAL TABLE nexus_chunks_fts USING fts5(
                chunk_id UNINDEXED,
                document_id UNINDEXED,
                title,
                section_path,
                text
            )
            """
        )
        conn.execute(
            """
            INSERT INTO nexus_chunks_fts(chunk_id, document_id, title, section_path, text)
            SELECT chunk_id, document_id, title, section_path, text
            FROM nexus_chunks
            """
        )
        conn.commit()


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys=ON;")
    for sql in SCHEMA_SQL:
        conn.execute(sql)
    _ensure_compat_migrations(conn)


def _connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(NEXUS_PATHS.db_path)
    conn.row_factory = sqlite3.Row
    return conn


_INIT_LOCK = threading.Lock()
_INITIALIZED = False


def initialize_storage() -> Path:
    """`CA_DATA_DIR/nexus/nexus.db` と必要ディレクトリを初期化する。"""
    global _INITIALIZED
    if _INITIALIZED:
        return NEXUS_PATHS.db_path
    with _INIT_LOCK:
        if _INITIALIZED:
            return NEXUS_PATHS.db_path
        ensure_dir(NEXUS_PATHS.ca_data_dir)
        for directory in REQUIRED_DIRS:
            ensure_dir(directory)

        with _connect_db() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            _ensure_schema(conn)
            conn.commit()
        _INITIALIZED = True

    return NEXUS_PATHS.db_path


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    """Nexus DB接続。"""
    conn = _connect_db()
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
            "INSERT OR REPLACE INTO nexus_chunks_fts(chunk_id, document_id, title, section_path, text) VALUES(?, ?, ?, ?, ?)",
            (chunk_id, document_id, title, section_path, content),
        )
        conn.commit()


DB_PATH = NEXUS_PATHS.db_path
NEXUS_DIR = NEXUS_PATHS.nexus_dir

# import時に初期化
initialize_storage()
