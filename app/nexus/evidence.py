from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import uuid

from app.nexus.db import get_conn, transaction


@dataclass(slots=True)
class EvidenceItem:
    """Persistable evidence item used for report grounding."""

    chunk_id: str
    citation_label: str
    source_url: str
    retrieved_at: str
    note: str | None = None
    quote: str | None = None
    metadata: dict = field(default_factory=dict)
    evidence_id: str = field(default_factory=lambda: str(uuid.uuid4()))



def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()



def save_evidence_items(job_id: str, items: list[EvidenceItem]) -> int:
    """Save evidence rows for a report job.

    retrieved_at and source_url are mandatory and validated for every item.
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
            if not item.source_url:
                raise ValueError("source_url is required")
            conn.execute(
                """
                INSERT OR REPLACE INTO nexus_evidence (
                    evidence_id, job_id, chunk_id, citation_label, source_url,
                    retrieved_at, note, quote, metadata, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.evidence_id,
                    job_id,
                    item.chunk_id,
                    item.citation_label,
                    item.source_url,
                    item.retrieved_at,
                    item.note,
                    item.quote,
                    json.dumps(item.metadata, ensure_ascii=False),
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
        if not source_url:
            source_url = f"nexus://document/{chunk.get('document_id', 'unknown')}"

        score = row.get("score")
        metadata = {
            "source": "library_search",
            "document": document,
            "score": float(score) if score is not None else None,
            "section_path": chunk.get("section_path"),
            "page_start": chunk.get("page_start"),
            "page_end": chunk.get("page_end"),
        }

        items.append(
            EvidenceItem(
                chunk_id=str(chunk.get("chunk_id") or ""),
                citation_label=str(chunk.get("citation_label") or row.get("citation_label") or ""),
                source_url=source_url,
                retrieved_at=ts,
                note=note or "library_search",
                quote=str(chunk.get("text") or ""),
                metadata=metadata,
            )
        )

    return items



def list_evidence_items(job_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT evidence_id, job_id, chunk_id, citation_label, source_url,
                   retrieved_at, note, quote, metadata, created_at
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
            "chunk_id": row["chunk_id"],
            "citation_label": row["citation_label"],
            "source_url": row["source_url"],
            "retrieved_at": row["retrieved_at"],
            "note": row["note"],
            "quote": row["quote"],
            "metadata": json.loads(row["metadata"] or "{}"),
            "created_at": row["created_at"],
        }
        for row in rows
    ]
