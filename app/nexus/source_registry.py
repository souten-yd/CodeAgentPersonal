from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import uuid
from urllib.parse import urlparse

from app.nexus.db import get_conn, insert_chunk, insert_document, update_document_artifact_paths
from app.nexus.jobs import append_job_event, update_job

_MIN_CHUNK_SIZE = 800
_MAX_CHUNK_SIZE = 1200
_DEFAULT_CHUNK_SIZE = 1000
_MIN_OVERLAP = 100
_MAX_OVERLAP = 200
_DEFAULT_OVERLAP = 150


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _chunk_text(text: str) -> list[str]:
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return []

    chunk_size = min(_MAX_CHUNK_SIZE, max(_MIN_CHUNK_SIZE, _DEFAULT_CHUNK_SIZE))
    overlap = min(_MAX_OVERLAP, max(_MIN_OVERLAP, _DEFAULT_OVERLAP))

    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + chunk_size)
        chunk = cleaned[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(cleaned):
            break
        start = max(start + 1, end - overlap)
    return chunks


def _read_text_for_ingest(source: dict) -> tuple[str, str, str, str]:
    text_raw = str(source.get("local_text_path") or "").strip()
    markdown_raw = str(source.get("local_markdown_path") or "").strip()
    original_raw = str(source.get("local_original_path") or "").strip()

    text_path = Path(text_raw) if text_raw else None
    markdown_path = Path(markdown_raw) if markdown_raw else None
    original_path = Path(original_raw) if original_raw else None

    text = ""
    if text_path is not None and text_path.exists() and text_path.is_file():
        text = text_path.read_text(encoding="utf-8", errors="replace")
    elif markdown_path is not None and markdown_path.exists() and markdown_path.is_file():
        text = markdown_path.read_text(encoding="utf-8", errors="replace")

    return text, str(original_path or ""), str(text_path or ""), str(markdown_path or "")


def _ingest_source_document(*, job_id: str, project: str, source: dict) -> str:
    source_id = str(source.get("source_id") or "").strip()
    if not source_id:
        return ""

    text, original_path, text_path, markdown_path = _read_text_for_ingest(source)
    if not text:
        return ""

    append_job_event(
        job_id,
        "state_transition",
        {
            "state": "ingesting_to_library",
            "status": "running",
            "message": "ingesting_to_library",
            "progress": 0.75,
            "source_id": source_id,
            "updated_at": _now_iso(),
        },
    )
    update_job(job_id, status="running", message="ingesting_to_library", progress=0.75)

    now = _now_iso()
    document_id = str(source.get("document_id") or source.get("linked_document_id") or "").strip() or str(uuid.uuid4())
    filename = str(source.get("title") or "").strip() or f"source_{source_id}.txt"
    content_type = str(source.get("content_type") or "text/plain").strip() or "text/plain"
    doc_path = original_path or text_path or markdown_path

    with get_conn() as conn:
        existing = conn.execute("SELECT id FROM nexus_documents WHERE id = ?", (document_id,)).fetchone()
    if existing is None:
        digest_source = Path(doc_path).read_bytes() if doc_path and Path(doc_path).exists() else text.encode("utf-8")
        insert_document(
            document_id=document_id,
            project=project,
            filename=filename,
            size=len(digest_source),
            content_type=content_type,
            path=doc_path,
            sha256=sha256(digest_source).hexdigest(),
            created_at=now,
        )

    update_document_artifact_paths(
        document_id=document_id,
        extracted_text_path=text_path,
        markdown_path=markdown_path,
        updated_at=now,
    )

    chunks = _chunk_text(text)
    for idx, chunk in enumerate(chunks):
        chunk_id = f"{document_id}:{idx}"
        citation_label = f"{filename}#{idx + 1}"
        insert_chunk(
            chunk_id=chunk_id,
            document_id=document_id,
            chunk_index=idx,
            title=filename,
            section_path="/",
            content=chunk,
            page_start=1,
            page_end=1,
            citation_label=citation_label,
            created_at=now,
        )

    with get_conn() as conn:
        conn.execute(
            "UPDATE nexus_sources SET linked_document_id = ?, updated_at = ? WHERE source_id = ?",
            (document_id, now, source_id),
        )
        conn.execute("DELETE FROM nexus_source_chunks WHERE source_id = ?", (source_id,))
        for idx, _ in enumerate(chunks):
            conn.execute(
                """
                INSERT INTO nexus_source_chunks(id, source_id, document_id, chunk_id, page_start, page_end,
                                                section_path, citation_label, created_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    source_id,
                    document_id,
                    f"{document_id}:{idx}",
                    1,
                    1,
                    "/",
                    f"{filename}#{idx + 1}",
                    now,
                ),
            )
        conn.commit()

    return document_id


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
                "SELECT source_id, linked_document_id FROM nexus_sources WHERE job_id = ? AND url = ?",
                (job_id, url),
            ).fetchone()

            domain = urlparse(url).netloc.lower()
            if existing is None:
                source_id = str(source.get("source_id") or uuid.uuid4())
                linked_document_id = str(source.get("document_id") or "")
                conn.execute(
                    """
                    INSERT INTO nexus_sources(
                        source_id, job_id, project, source_type, url, final_url, title,
                        publisher, language, domain, content_type,
                        local_original_path, local_text_path, local_markdown_path, local_screenshot_path,
                        linked_document_id, status, error, retrieved_at, created_at, updated_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        source_id,
                        job_id,
                        project,
                        str(source.get("source_type") or "web"),
                        url,
                        str(source.get("final_url") or url),
                        str(source.get("title") or ""),
                        str(source.get("publisher") or ""),
                        str(source.get("language") or ""),
                        domain,
                        str(source.get("content_type") or ""),
                        str(source.get("local_original_path") or ""),
                        str(source.get("local_text_path") or ""),
                        str(source.get("local_markdown_path") or ""),
                        str(source.get("local_screenshot_path") or ""),
                        linked_document_id,
                        str(source.get("status") or "queued"),
                        str(source.get("error") or ""),
                        str(source.get("retrieved_at") or now),
                        now,
                        now,
                    ),
                )
            else:
                source_id = str(existing["source_id"])
                linked_document_id = str(source.get("document_id") or existing["linked_document_id"] or "")
                conn.execute(
                    """
                    UPDATE nexus_sources
                    SET final_url = ?, title = ?, publisher = ?, language = ?, content_type = ?,
                        local_original_path = ?, local_text_path = ?, local_markdown_path = ?, local_screenshot_path = ?,
                        linked_document_id = ?, status = ?, error = ?, retrieved_at = ?, updated_at = ?
                    WHERE source_id = ?
                    """,
                    (
                        str(source.get("final_url") or url),
                        str(source.get("title") or ""),
                        str(source.get("publisher") or ""),
                        str(source.get("language") or ""),
                        str(source.get("content_type") or ""),
                        str(source.get("local_original_path") or ""),
                        str(source.get("local_text_path") or ""),
                        str(source.get("local_markdown_path") or ""),
                        str(source.get("local_screenshot_path") or ""),
                        linked_document_id,
                        str(source.get("status") or "queued"),
                        str(source.get("error") or ""),
                        str(source.get("retrieved_at") or now),
                        now,
                        source_id,
                    ),
                )

            saved_rows.append({**source, "source_id": source_id, "domain": domain, "linked_document_id": linked_document_id})

        conn.commit()

    enriched_rows: list[dict] = []
    for row in saved_rows:
        document_id = _ingest_source_document(job_id=job_id, project=project, source=row)
        if document_id:
            row = {**row, "document_id": document_id, "linked_document_id": document_id, "status": "ingested"}
        enriched_rows.append(row)

    return enriched_rows
