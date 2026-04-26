from __future__ import annotations

from dataclasses import dataclass
import json
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


def _parse_json_object(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _matches_filters(row: dict, filters: dict) -> bool:
    if not filters:
        return True

    for key, expected in filters.items():
        actual = row.get(key)
        if isinstance(expected, list):
            if actual not in expected:
                return False
        elif actual != expected:
            return False
    return True


def search_evidence(
    query: str,
    *,
    limit: int = 10,
    scope: str | None = None,
    doc_types: list[str] | None = None,
    filters: dict | None = None,
) -> list[dict]:
    limit = max(1, min(100, limit))
    filters = filters or {}
    normalized_doc_types = {value.strip().lower() for value in (doc_types or []) if value and value.strip()}

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                c.chunk_id,
                nexus_chunks_fts.document_id,
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
                d.metadata,
                d.source_metadata,
                d.doc_metadata,
                d.created_at
            FROM nexus_chunks_fts
            JOIN nexus_chunks c ON c.chunk_id = nexus_chunks_fts.chunk_id
            JOIN nexus_documents d ON d.id = nexus_chunks_fts.document_id
            WHERE nexus_chunks_fts MATCH ?
            ORDER BY score
            """,
            (query,),
        ).fetchall()

    scope_normalized = (scope or "").strip().lower()
    candidates: list[dict] = []
    for row in rows:
        content_type = str(row["content_type"] or "").strip().lower()
        ext = str(row["filename"] or "").rsplit(".", 1)
        extension = ext[-1].lower() if len(ext) > 1 else ""
        doc_type = extension or content_type

        metadata = _parse_json_object(row["metadata"])
        source_metadata = _parse_json_object(row["source_metadata"])
        doc_metadata = _parse_json_object(row["doc_metadata"])

        filter_source = {
            "project": row["project"],
            "document_id": row["document_id"],
            "filename": row["filename"],
            "content_type": row["content_type"],
            "doc_type": doc_type,
            "scope": source_metadata.get("scope") or metadata.get("scope") or doc_metadata.get("scope"),
            **metadata,
            **source_metadata,
            **doc_metadata,
        }

        if scope_normalized:
            row_scope = str(filter_source.get("scope") or "").strip().lower()
            if row_scope != scope_normalized:
                continue
        if normalized_doc_types and doc_type not in normalized_doc_types and content_type not in normalized_doc_types:
            continue
        if not _matches_filters(filter_source, filters):
            continue

        candidates.append(
            {
                "chunk_id": row["chunk_id"],
                "document_id": row["document_id"],
                "title": row["title"],
                "section_path": row["section_path"],
                "page_start": row["page_start"],
                "page_end": row["page_end"],
                "snippet": row["text"],
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
        if len(candidates) >= limit:
            break
    return candidates
