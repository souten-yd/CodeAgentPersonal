from __future__ import annotations

from collections.abc import Iterable
import re


def _normalize_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _source_chunk_index(source_chunks: Iterable[dict] | None) -> dict[tuple[str, str], dict]:
    index: dict[tuple[str, str], dict] = {}
    for row in source_chunks or []:
        source_id = str(row.get("source_id") or "").strip()
        chunk_id = str(row.get("chunk_id") or "").strip()
        if not source_id and not chunk_id:
            continue
        index[(source_id, chunk_id)] = row
        if source_id:
            index.setdefault((source_id, ""), row)
        if chunk_id:
            index.setdefault(("", chunk_id), row)
    return index


def build_citation_map(
    evidence: list[dict],
    source_chunks: list[dict] | None = None,
) -> list[dict]:
    """evidence / chunk / source の対応表を生成する。"""
    mapped: list[dict] = []
    chunk_index = _source_chunk_index(source_chunks)

    for index, item in enumerate(evidence, start=1):
        source_id = str(item.get("source_id") or item.get("id") or "").strip()
        chunk_id = str(item.get("chunk_id") or "").strip()

        mapping = (
            chunk_index.get((source_id, chunk_id))
            or chunk_index.get((source_id, ""))
            or chunk_index.get(("", chunk_id))
            or {}
        )

        url = str(item.get("url") or item.get("source_url") or mapping.get("url") or "")
        local_path = str(
            item.get("local_path")
            or item.get("local_markdown_path")
            or item.get("local_text_path")
            or item.get("local_original_path")
            or mapping.get("local_path")
            or mapping.get("local_markdown_path")
            or mapping.get("local_text_path")
            or mapping.get("local_original_path")
            or ""
        )

        citation_label = str(
            item.get("citation_label")
            or mapping.get("citation_label")
            or f"[{index}]"
        )

        mapped.append(
            {
                "citation_label": citation_label,
                "title": str(item.get("title") or mapping.get("title") or ""),
                "source_type": str(item.get("source_type") or mapping.get("source_type") or ""),
                "url": url,
                "local_path": local_path,
                "page_start": _normalize_int(item.get("page_start") or mapping.get("page_start")),
                "page_end": _normalize_int(item.get("page_end") or mapping.get("page_end")),
                "quote": str(item.get("quote") or mapping.get("quote") or ""),
                "source_id": source_id or str(mapping.get("source_id") or ""),
                "chunk_id": chunk_id or str(mapping.get("chunk_id") or ""),
            }
        )
    return mapped


def _normalize_key(item: dict) -> tuple[str, str]:
    source_id = str(item.get("source_id") or item.get("id") or "").strip()
    chunk_id = str(item.get("chunk_id") or "").strip()
    return source_id, chunk_id


def _build_label_indexes(references: list[dict]) -> tuple[dict[tuple[str, str], str], dict[str, str]]:
    by_key: dict[tuple[str, str], str] = {}
    by_old_label: dict[str, str] = {}
    for idx, reference in enumerate(references, start=1):
        label = f"[S{idx}]"
        source_id, chunk_id = _normalize_key(reference)
        old_label = str(reference.get("citation_label") or "").strip()
        if old_label:
            by_old_label[old_label] = label
        if source_id or chunk_id:
            by_key[(source_id, chunk_id)] = label
            if source_id:
                by_key.setdefault((source_id, ""), label)
            if chunk_id:
                by_key.setdefault(("", chunk_id), label)
    return by_key, by_old_label


def _normalize_items(
    items: list[dict] | None,
    *,
    by_key: dict[tuple[str, str], str],
    by_old_label: dict[str, str],
) -> list[dict]:
    normalized: list[dict] = []
    for item in items or []:
        row = dict(item)
        source_id, chunk_id = _normalize_key(row)
        current_label = str(row.get("citation_label") or "").strip()
        next_label = (
            by_key.get((source_id, chunk_id))
            or by_key.get((source_id, ""))
            or by_key.get(("", chunk_id))
            or by_old_label.get(current_label)
            or current_label
        )
        if next_label:
            row["citation_label"] = next_label
        normalized.append(row)
    return normalized


def replace_citation_labels(text: str, label_map: dict[str, str]) -> str:
    normalized = str(text or "")
    for old, new in sorted(label_map.items(), key=lambda pair: len(pair[0]), reverse=True):
        if not old or old == new:
            continue
        normalized = re.sub(re.escape(old), new, normalized)
    return normalized


def normalize_reference_labels(
    *,
    references: list[dict],
    evidence_json: list[dict] | None = None,
    evidence_chunks: list[dict] | None = None,
) -> dict:
    normalized_references: list[dict] = []
    by_old_label: dict[str, str] = {}

    for idx, reference in enumerate(references, start=1):
        row = dict(reference)
        new_label = f"[S{idx}]"
        old_label = str(row.get("citation_label") or "").strip()
        if old_label:
            by_old_label[old_label] = new_label
        row["citation_label"] = new_label
        normalized_references.append(row)

    by_key, _ = _build_label_indexes(normalized_references)
    normalized_evidence_json = _normalize_items(evidence_json, by_key=by_key, by_old_label=by_old_label)
    normalized_evidence_chunks = _normalize_items(evidence_chunks, by_key=by_key, by_old_label=by_old_label)
    return {
        "references": normalized_references,
        "evidence_json": normalized_evidence_json,
        "evidence_chunks": normalized_evidence_chunks,
        "label_map": by_old_label,
    }
