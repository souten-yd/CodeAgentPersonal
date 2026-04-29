from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import uuid
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from app.nexus.db import get_conn, insert_chunk, insert_document, update_document_artifact_paths
from app.nexus.jobs import append_job_event, ensure_job_exists, update_job

_MIN_CHUNK_SIZE = 800
_MAX_CHUNK_SIZE = 1200
_DEFAULT_CHUNK_SIZE = 1000
_MIN_OVERLAP = 100
_MAX_OVERLAP = 200
_DEFAULT_OVERLAP = 150



_TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid"}


def canonicalize_source_url(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "").lower()
    host = (parsed.hostname or "").lower()
    netloc = host
    if parsed.port:
        netloc = f"{host}:{parsed.port}"
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    kept = []
    for k, v in parse_qsl(parsed.query, keep_blank_values=True):
        if k.lower() in _TRACKING_PARAMS:
            continue
        kept.append((k, v))
    kept.sort(key=lambda x: (x[0], x[1]))
    query = urlencode(kept, doseq=True)
    return urlunparse((scheme, netloc, path, "", query, ""))


def find_reusable_artifact(canonical_url: str = "", content_sha256: str = "") -> dict | None:
    with get_conn() as conn:
        if canonical_url:
            row = conn.execute(
                "SELECT * FROM nexus_source_artifacts WHERE canonical_url = ? ORDER BY updated_at DESC LIMIT 1",
                (canonical_url,),
            ).fetchone()
            if row is not None:
                return dict(row)
        if content_sha256:
            row = conn.execute(
                "SELECT * FROM nexus_source_artifacts WHERE content_sha256 = ? ORDER BY updated_at DESC LIMIT 1",
                (content_sha256,),
            ).fetchone()
            if row is not None:
                return dict(row)
    return None


def upsert_source_artifact(*, source_id: str, canonical_url: str, final_url: str, content_sha256: str, content_type: str, local_original_path: str, local_text_path: str, local_markdown_path: str) -> str:
    now = _now_iso()
    existing = find_reusable_artifact(canonical_url=canonical_url, content_sha256=content_sha256)
    with get_conn() as conn:
        if existing is not None:
            artifact_id = str(existing.get("artifact_id") or "")
            conn.execute("""
                UPDATE nexus_source_artifacts
                SET source_id=?, canonical_url=?, final_url=?, content_sha256=?, content_type=?,
                    local_original_path=?, local_text_path=?, local_markdown_path=?, updated_at=?
                WHERE artifact_id=?
            """, (source_id, canonical_url, final_url, content_sha256, content_type, local_original_path, local_text_path, local_markdown_path, now, artifact_id))
            conn.commit()
            return artifact_id
        artifact_id = str(uuid.uuid4())
        conn.execute("""
            INSERT INTO nexus_source_artifacts(artifact_id, source_id, canonical_url, final_url, content_sha256, content_type, local_original_path, local_text_path, local_markdown_path, created_at, updated_at)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (artifact_id, source_id, canonical_url, final_url, content_sha256, content_type, local_original_path, local_text_path, local_markdown_path, now, now))
        conn.commit()
    return artifact_id


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
            chunk_id = f"{document_id}:{idx}".strip()
            if not document_id or not chunk_id:
                continue
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
                    chunk_id,
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
    ensure_job_exists(job_id, title="research source registry", message="registering sources", status="running")
    saved_rows: list[dict] = []
    with get_conn() as conn:
        for source in sources:
            url = str(source.get("url") or "").strip()
            if not url:
                continue
            raw = str(source.get("document_id") or source.get("linked_document_id") or "").strip()
            linked_document_id = raw or None

            existing = conn.execute(
                "SELECT source_id, linked_document_id FROM nexus_sources WHERE job_id = ? AND url = ?",
                (job_id, url),
            ).fetchone()

            domain = urlparse(url).netloc.lower()
            canonical_url = canonicalize_source_url(url)
            if existing is None:
                source_id = str(source.get("source_id") or uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO nexus_sources(
                        source_id, job_id, project, source_type, url, final_url, title,
                        publisher, language, domain, content_type,
                        local_original_path, local_text_path, local_markdown_path, local_screenshot_path,
                        linked_document_id, status, source_score, source_score_breakdown, error, retrieved_at, canonical_url, content_sha256, is_duplicate, duplicate_of_source_id, created_at, updated_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        float(source.get("source_score") or 0.0),
                        json.dumps(source.get("source_score_breakdown") or {}, ensure_ascii=False, sort_keys=True),
                        str(source.get("error") or ""),
                        str(source.get("retrieved_at") or now),
                        canonical_url,
                        str(source.get("content_sha256") or ""),
                        int(source.get("is_duplicate") or 0),
                        str(source.get("duplicate_of_source_id") or ""),
                        now,
                        now,
                    ),
                )
            else:
                source_id = str(existing["source_id"])
                if linked_document_id is None:
                    existing_raw = str(existing["linked_document_id"] or "").strip()
                    linked_document_id = existing_raw or None
                conn.execute(
                    """
                    UPDATE nexus_sources
                    SET final_url = ?, title = ?, publisher = ?, language = ?, content_type = ?,
                        local_original_path = ?, local_text_path = ?, local_markdown_path = ?, local_screenshot_path = ?,
                        linked_document_id = ?, status = ?, source_score = ?, source_score_breakdown = ?,
                        error = ?, retrieved_at = ?, canonical_url = ?, content_sha256 = ?, is_duplicate = ?, duplicate_of_source_id = ?, updated_at = ?
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
                        float(source.get("source_score") or 0.0),
                        json.dumps(source.get("source_score_breakdown") or {}, ensure_ascii=False, sort_keys=True),
                        str(source.get("error") or ""),
                        str(source.get("retrieved_at") or now),
                        canonical_url,
                        str(source.get("content_sha256") or ""),
                        int(source.get("is_duplicate") or 0),
                        str(source.get("duplicate_of_source_id") or ""),
                        now,
                        source_id,
                    ),
                )

            saved_rows.append(
                {
                    **source,
                    "source_id": source_id,
                    "domain": domain,
                    "linked_document_id": linked_document_id or "",
                }
            )

        conn.commit()

    enriched_rows: list[dict] = []
    for row in saved_rows:
        document_id = _ingest_source_document(job_id=job_id, project=project, source=row)
        if document_id:
            row = {**row, "document_id": document_id, "linked_document_id": document_id, "status": "ingested"}
        enriched_rows.append(row)

    return enriched_rows
