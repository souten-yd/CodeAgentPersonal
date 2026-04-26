from __future__ import annotations

from urllib.parse import urlparse


def _normalize_url(raw_url: str) -> str:
    parsed = urlparse((raw_url or "").strip())
    if parsed.scheme not in {"http", "https"}:
        return ""
    if not parsed.netloc:
        return ""
    normalized_path = parsed.path or "/"
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{normalized_path}"


def collect_source_candidates(
    *,
    search_items: list[dict] | None = None,
    manual_urls: list[str] | None = None,
) -> list[dict]:
    """検索結果と手動URLを統合し、重複除去済みの source 候補を返す。"""
    candidates: list[dict] = []
    seen_urls: set[str] = set()

    for item in search_items or []:
        normalized_url = _normalize_url(str(item.get("url") or ""))
        if not normalized_url or normalized_url in seen_urls:
            continue
        seen_urls.add(normalized_url)
        candidates.append(
            {
                "url": normalized_url,
                "title": str(item.get("title") or ""),
                "snippet": str(item.get("snippet") or ""),
                "provider": str(item.get("provider") or ""),
                "source_type": "web",
                "origin": "search",
            }
        )

    for raw_url in manual_urls or []:
        normalized_url = _normalize_url(str(raw_url or ""))
        if not normalized_url or normalized_url in seen_urls:
            continue
        seen_urls.add(normalized_url)
        candidates.append(
            {
                "url": normalized_url,
                "title": "",
                "snippet": "",
                "provider": "manual",
                "source_type": "web",
                "origin": "manual",
            }
        )

    return candidates
