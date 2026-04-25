from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.nexus.db import get_conn


@dataclass
class EvidenceCandidate:
    chunk_id: str
    document_id: str
    score: float
    title: str
    section_path: str
    text: str
    page_start: int
    page_end: int
    citation_label: str
    metadata: dict


class VectorIndex(Protocol):
    """Future extension point (FAISS / Chroma etc.)."""

    # Intentionally empty marker interface for future implementations.
    pass


class NullVectorIndex:
    """No-op implementation used until vector search is introduced."""

    def upsert(self, document_id: str, chunks: list[dict]) -> None:
        return None

    def search(self, query: str, top_k: int = 10) -> list[EvidenceCandidate]:
        return []


def search_evidence(query: str, top_k: int = 10) -> list[dict]:
    top_k = max(1, min(100, top_k))
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                c.chunk_id,
                c.document_id,
                c.title,
                c.section_path,
                c.text,
                c.page_start,
                c.page_end,
                c.citation_label,
                bm25(nexus_chunks_fts) AS score,
                d.project,
                d.filename,
                d.path,
                d.content_type,
                d.sha256,
                d.created_at
            FROM nexus_chunks_fts
            JOIN nexus_chunks c ON c.chunk_id = nexus_chunks_fts.chunk_id
            JOIN nexus_documents d ON d.id = c.document_id
            WHERE nexus_chunks_fts MATCH ?
            ORDER BY score
            LIMIT ?
            """,
            (query, top_k),
        ).fetchall()

    candidates: list[dict] = []
    for row in rows:
        candidates.append(
            {
                "type": "evidence_candidate",
                "score": float(row["score"]),
                "citation_label": row["citation_label"],
                "chunk": {
                    "chunk_id": row["chunk_id"],
                    "document_id": row["document_id"],
                    "title": row["title"],
                    "section_path": row["section_path"],
                    "text": row["text"],
                    "page_start": row["page_start"],
                    "page_end": row["page_end"],
                    "citation_label": row["citation_label"],
                },
                "document": {
                    "project": row["project"],
                    "filename": row["filename"],
                    "path": row["path"],
                    "content_type": row["content_type"],
                    "sha256": row["sha256"],
                    "created_at": row["created_at"],
                },
            }
        )
    return candidates
