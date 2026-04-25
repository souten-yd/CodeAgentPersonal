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
