from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Protocol, TypedDict

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


class IndexChunk(TypedDict, total=False):
    """Vector indexに投入する最小チャンク構造。"""

    chunk_id: str
    document_id: str
    text: str
    metadata: dict[str, Any]


class VectorSearchHit(TypedDict):
    """将来の実装差し替え時に共通利用する検索結果の最小構造。"""

    chunk_id: str
    document_id: str
    score: float
    snippet: str


class VectorIndex(Protocol):
    """Future extension point (FAISS / Chroma etc.)."""

    def add_chunks(self, chunks: list[IndexChunk]) -> None:
        ...

    def search(self, query: str, limit: int = 20) -> list[VectorSearchHit]:
        ...


class NullVectorIndex:
    """No-op implementation used until vector search is introduced."""

    def add_chunks(self, chunks: list[IndexChunk]) -> None:
        return None

    def upsert(self, document_id: str, chunks: list[IndexChunk]) -> None:
        """Backward-compatible wrapper: upsert -> add_chunks."""
        normalized_chunks: list[IndexChunk] = []
        for chunk in chunks:
            merged_chunk: IndexChunk = dict(chunk)
            if not merged_chunk.get("document_id"):
                merged_chunk["document_id"] = document_id
            normalized_chunks.append(merged_chunk)
        self.add_chunks(normalized_chunks)

    def search(self, query: str, limit: int = 20) -> list[VectorSearchHit]:
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


def _normalize_scope(scope: str | list[str] | None) -> list[str]:
    if scope is None:
        return []
    raw_values = [scope] if isinstance(scope, str) else scope
    normalized: list[str] = []
    for value in raw_values:
        trimmed = str(value or "").strip().lower()
        if trimmed and trimmed not in normalized:
            normalized.append(trimmed)
    return normalized


def _normalize_doc_types(doc_types: list[str] | None) -> list[str]:
    normalized: list[str] = []
    for value in doc_types or []:
        trimmed = str(value or "").strip().lower()
        if trimmed and trimmed not in normalized:
            normalized.append(trimmed)
    return normalized


def _normalize_filters(filters: dict | None) -> dict:
    normalized: dict = {}
    for key, expected in (filters or {}).items():
        normalized_key = str(key).strip()
        if not normalized_key:
            continue
        if isinstance(expected, list):
            values = []
            for item in expected:
                if isinstance(item, str):
                    item = item.strip()
                if item in ("", None):
                    continue
                values.append(item)
            normalized[normalized_key] = values
            continue
        if isinstance(expected, str):
            expected = expected.strip()
            if expected == "":
                continue
        normalized[normalized_key] = expected
    return normalized


def search_evidence(
    query: str,
    *,
    limit: int = 10,
    scope: str | list[str] | None = None,
    doc_types: list[str] | None = None,
    filters: dict | None = None,
) -> tuple[list[dict], dict]:
    limit = max(1, min(100, limit))
    normalized_scope = _normalize_scope(scope)
    normalized_scope_set = set(normalized_scope)
    normalized_doc_types = _normalize_doc_types(doc_types)
    normalized_doc_types_set = set(normalized_doc_types)
    normalized_filters = _normalize_filters(filters)
    applied_filters = {
        "scope": normalized_scope,
        "doc_types": normalized_doc_types,
        "filters": normalized_filters,
    }

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

        if normalized_scope_set:
            row_scope = str(filter_source.get("scope") or "").strip().lower()
            if row_scope not in normalized_scope_set:
                continue
        if normalized_doc_types_set and doc_type not in normalized_doc_types_set and content_type not in normalized_doc_types_set:
            continue
        if not _matches_filters(filter_source, normalized_filters):
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
    return candidates, applied_filters
