from __future__ import annotations

from collections.abc import Iterable


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
