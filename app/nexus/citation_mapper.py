from __future__ import annotations


def build_citation_map(evidence: list[dict]) -> list[dict]:
    """evidence / chunk / source の対応表を生成する。"""
    mapped: list[dict] = []
    for index, item in enumerate(evidence, start=1):
        mapped.append(
            {
                "citation_label": f"[{index}]",
                "evidence_id": str(item.get("evidence_id") or ""),
                "chunk_id": str(item.get("chunk_id") or ""),
                "document_id": str(item.get("document_id") or ""),
                "source_id": str(item.get("source_id") or item.get("id") or ""),
                "source_url": str(item.get("url") or item.get("source_url") or ""),
                "title": str(item.get("title") or ""),
            }
        )
    return mapped
