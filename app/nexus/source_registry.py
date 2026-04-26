from __future__ import annotations

from datetime import datetime, timezone
import uuid
from urllib.parse import urlparse

from app.nexus.db import get_conn


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def register_or_update_sources(
    *,
    job_id: str,
    project: str,
    sources: list[dict],
) -> list[dict]:
    now = _now_iso()
    saved_rows: list[dict] = []
    with get_conn() as conn:
        for source in sources:
            url = str(source.get("url") or "").strip()
            if not url:
                continue

            existing = conn.execute(
                "SELECT source_id FROM nexus_sources WHERE job_id = ? AND url = ?",
                (job_id, url),
            ).fetchone()

            domain = urlparse(url).netloc.lower()
            if existing is None:
                source_id = str(source.get("source_id") or uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO nexus_sources(
                        source_id, job_id, project, source_type, url, final_url, title,
                        domain, content_type, linked_document_id, status, error,
                        retrieved_at, created_at, updated_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        source_id,
                        job_id,
                        project,
                        str(source.get("source_type") or "web"),
                        url,
                        str(source.get("final_url") or url),
                        str(source.get("title") or ""),
                        domain,
                        str(source.get("content_type") or ""),
                        str(source.get("document_id") or ""),
                        str(source.get("status") or "queued"),
                        str(source.get("error") or ""),
                        str(source.get("retrieved_at") or now),
                        now,
                        now,
                    ),
                )
            else:
                source_id = str(existing["source_id"])
                conn.execute(
                    """
                    UPDATE nexus_sources
                    SET final_url = ?, title = ?, content_type = ?, linked_document_id = ?,
                        status = ?, error = ?, retrieved_at = ?, updated_at = ?
                    WHERE source_id = ?
                    """,
                    (
                        str(source.get("final_url") or url),
                        str(source.get("title") or ""),
                        str(source.get("content_type") or ""),
                        str(source.get("document_id") or ""),
                        str(source.get("status") or "queued"),
                        str(source.get("error") or ""),
                        str(source.get("retrieved_at") or now),
                        now,
                        source_id,
                    ),
                )

            saved_rows.append({**source, "source_id": source_id, "domain": domain})

        conn.commit()
    return saved_rows
