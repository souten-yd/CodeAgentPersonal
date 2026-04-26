from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import uuid

from app.nexus.db import get_conn, transaction


@dataclass(slots=True)
class EvidenceItem:
    """Persistable evidence item used for report grounding."""

    source_type: str
    document_id: str
    chunk_id: str
    url: str
    retrieved_at: str
    title: str = ""
    publisher: str = ""
    published_date: str = ""
    relevance_score: float = 0.0
    credibility_score: float = 0.0
    freshness_score: float = 0.0
    evidence_level: str = ""
    metadata_json: dict = field(default_factory=dict)
    citation_label: str = ""
    note: str | None = None
    quote: str | None = None
    evidence_id: str = field(default_factory=lambda: str(uuid.uuid4()))



def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()



def save_evidence_items(job_id: str, items: list[EvidenceItem]) -> int:
    """Save evidence rows for a report job.

    retrieved_at and url are mandatory and validated for every item.
    """
    if not job_id:
        raise ValueError("job_id is required")

    if not items:
        return 0

    created_at = _now_iso()
    with transaction() as conn:
        for item in items:
            if not item.retrieved_at:
                raise ValueError("retrieved_at is required")
            if not item.url:
                raise ValueError("url is required")
            conn.execute(
                """
                INSERT OR REPLACE INTO nexus_evidence (
                    evidence_id, job_id, source_type, document_id, chunk_id, title,
                    citation_label, source_url, publisher, published_date,
                    retrieved_at, note, quote, relevance, credibility, freshness,
                    evidence_level, metadata_json, metadata,
                    url, relevance_score, credibility_score, freshness_score, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.evidence_id,
                    job_id,
                    item.source_type,
                    item.document_id,
                    item.chunk_id,
                    item.title,
                    item.citation_label,
                    item.url,
                    item.publisher,
                    item.published_date,
                    item.retrieved_at,
                    item.note,
                    item.quote,
                    float(item.relevance_score or 0.0),
                    float(item.credibility_score or 0.0),
                    float(item.freshness_score or 0.0),
                    item.evidence_level,
                    json.dumps(item.metadata_json, ensure_ascii=False),
                    json.dumps(item.metadata_json, ensure_ascii=False),
                    item.url,
                    float(item.relevance_score or 0.0),
                    float(item.credibility_score or 0.0),
                    float(item.freshness_score or 0.0),
                    created_at,
                ),
            )
    return len(items)



def build_library_evidence(
    search_results: list[dict],
    *,
    note: str | None = None,
    retrieved_at: str | None = None,
) -> list[EvidenceItem]:
    """Convert library search results (`search_evidence`) into EvidenceItem list."""
    ts = retrieved_at or _now_iso()
    items: list[EvidenceItem] = []

    for row in search_results:
        chunk = row.get("chunk") or {}
        document = row.get("document") or {}
        if not chunk:
            chunk = {
                "chunk_id": row.get("chunk_id"),
                "document_id": row.get("document_id"),
                "title": row.get("title"),
                "section_path": row.get("section_path"),
                "text": row.get("snippet"),
                "page_start": row.get("page_start"),
                "page_end": row.get("page_end"),
                "citation_label": row.get("citation_label"),
            }
        source_url = str(document.get("path") or "")
        document_id = str(chunk.get("document_id") or row.get("document_id") or "")
        if not source_url:
            source_url = f"nexus://document/{document_id or 'unknown'}"

        score = row.get("score")
        metadata = {
            "source": "library_search",
            "source_type": "library",
            "document": document,
            "score": float(score) if score is not None else None,
            "section_path": chunk.get("section_path"),
            "page_start": chunk.get("page_start"),
            "page_end": chunk.get("page_end"),
        }

        items.append(
            EvidenceItem(
                source_type="library",
                document_id=document_id,
                chunk_id=str(chunk.get("chunk_id") or ""),
                url=source_url,
                title=str(document.get("title") or chunk.get("title") or row.get("title") or ""),
                relevance_score=float(score) if score is not None else 0.0,
                citation_label=str(chunk.get("citation_label") or row.get("citation_label") or ""),
                retrieved_at=ts,
                note=note or "library_search",
                quote=str(chunk.get("text") or ""),
                metadata_json=metadata,
            )
        )

    return items



def list_evidence_items(job_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT evidence_id, job_id, source_type, document_id, chunk_id, source_url,
                   title, publisher, published_date, citation_label, retrieved_at,
                   note, quote, relevance, credibility, freshness, evidence_level,
                   metadata_json, metadata, url,
                   relevance_score, credibility_score, freshness_score,
                   created_at
            FROM nexus_evidence
            WHERE job_id = ?
            ORDER BY created_at ASC, evidence_id ASC
            """,
            (job_id,),
        ).fetchall()

    return [
        {
            "evidence_id": row["evidence_id"],
            "job_id": row["job_id"],
            "source_type": row["source_type"],
            "document_id": row["document_id"],
            "chunk_id": row["chunk_id"],
            "url": row["url"] or row["source_url"],
            "source_url": row["source_url"] or row["url"],
            "title": row["title"],
            "publisher": row["publisher"],
            "published_date": row["published_date"],
            "citation_label": row["citation_label"],
            "retrieved_at": row["retrieved_at"],
            "relevance_score": float(row["relevance_score"] or row["relevance"] or 0.0),
            "credibility_score": float(row["credibility_score"] or row["credibility"] or 0.0),
            "freshness_score": float(row["freshness_score"] or row["freshness"] or 0.0),
            "evidence_level": str(row["evidence_level"] or ""),
            "note": row["note"],
            "quote": row["quote"],
            "metadata_json": json.loads(row["metadata_json"] or row["metadata"] or "{}"),
            "metadata": json.loads(row["metadata_json"] or row["metadata"] or "{}"),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def list_evidence_table_items(
    job_id: str,
    *,
    source_type: str | None = None,
    filter_text: str | None = None,
    limit: int = 50,
) -> dict:
    """UI table binding ready evidence list with pagination envelope.

    Returns:
        {
            "total": int,
            "items": list[dict],
            "next_cursor": str | None,  # reserved for future paging
        }
    """
    normalized_limit = max(1, min(int(limit), 200))
    normalized_source_type = (source_type or "").strip().lower()
    normalized_filter = (filter_text or "").strip().lower()

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT evidence_id, job_id, source_type, document_id, chunk_id, source_url,
                   title, publisher, published_date, citation_label, retrieved_at, note,
                   quote, relevance, credibility, freshness, evidence_level,
                   metadata_json, metadata, url,
                   relevance_score, credibility_score, freshness_score,
                   created_at
            FROM nexus_evidence
            WHERE job_id = ?
            ORDER BY created_at DESC, evidence_id DESC
            """,
            (job_id,),
        ).fetchall()

    filtered_items: list[dict] = []
    for row in rows:
        metadata = json.loads(row["metadata_json"] or row["metadata"] or "{}")
        row_source_type = str(
            row["source_type"]
            or metadata.get("source_type")
            or metadata.get("source")
            or row["note"]
            or ""
        ).strip().lower()
        if normalized_source_type and row_source_type != normalized_source_type:
            continue

        searchable_parts = (
            str(row["citation_label"] or ""),
            str(row["url"] or row["source_url"] or ""),
            str(row["note"] or ""),
            str(row["quote"] or ""),
            str(row["title"] or ""),
            row_source_type,
        )
        searchable_text = " ".join(searchable_parts).lower()
        if normalized_filter and normalized_filter not in searchable_text:
            continue

        filtered_items.append(
            {
                "evidence_id": row["evidence_id"],
                "job_id": row["job_id"],
                "source_type": row_source_type,
                "document_id": str(row["document_id"] or ""),
                "chunk_id": row["chunk_id"],
                "url": row["url"] or row["source_url"],
                "title": str(row["title"] or ""),
                "publisher": str(row["publisher"] or ""),
                "published_date": str(row["published_date"] or ""),
                "citation_label": row["citation_label"],
                "citation": row["citation_label"],
                "retrieved_at": row["retrieved_at"],
                "relevance_score": float(row["relevance_score"] or row["relevance"] or 0.0),
                "credibility_score": float(row["credibility_score"] or row["credibility"] or 0.0),
                "freshness_score": float(row["freshness_score"] or row["freshness"] or 0.0),
                "relevance": float(row["relevance_score"] or row["relevance"] or 0.0),
                "credibility": float(row["credibility_score"] or row["credibility"] or 0.0),
                "freshness": float(row["freshness_score"] or row["freshness"] or 0.0),
                "evidence_level": str(row["evidence_level"] or ""),
                "metadata_json": metadata,
            }
        )

    total = len(filtered_items)
    return {
        "total": total,
        "items": filtered_items[:normalized_limit],
        "next_cursor": None,
    }
