from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from typing import Any
from urllib import parse, request

from app.nexus.evidence import EvidenceItem


_BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def plan_web_queries(topic: str, *, max_queries: int = 4) -> list[str]:
    """Build lightweight web-search queries from one topic string."""
    topic = (topic or "").strip()
    if not topic:
        return []

    seeds = [
        topic,
        f"{topic} latest",
        f"{topic} analysis",
        f"{topic} risks opportunities",
    ]

    unique: list[str] = []
    for query in seeds:
        q = " ".join(query.split())
        if q and q not in unique:
            unique.append(q)
        if len(unique) >= max(1, max_queries):
            break
    return unique


def run_web_search(
    queries: list[str],
    *,
    max_results_per_query: int = 5,
    country: str = "US",
    search_lang: str = "en",
) -> dict[str, Any]:
    """Run Brave Search when configured, otherwise return non-fatal stub results."""
    normalized_queries = [q.strip() for q in queries if (q or "").strip()]
    api_key = (os.environ.get("BRAVE_SEARCH_API_KEY") or "").strip()

    if not normalized_queries:
        return {
            "provider": "brave",
            "configured": bool(api_key),
            "items": [],
            "message": "query が空です。",
        }

    if not api_key:
        return {
            "provider": "brave",
            "configured": False,
            "message": "設定不足: BRAVE_SEARCH_API_KEY が未設定のため、Web検索はスタブ結果を返します。",
            "items": [
                {
                    "query": query,
                    "rank": 1,
                    "title": f"[stub] {query}",
                    "url": "",
                    "snippet": "BRAVE_SEARCH_API_KEY を設定すると実検索結果に切り替わります。",
                    "is_stub": True,
                }
                for query in normalized_queries
            ],
        }

    items: list[dict[str, Any]] = []
    errors: list[str] = []
    for query in normalized_queries:
        params = parse.urlencode(
            {
                "q": query,
                "count": max(1, min(20, max_results_per_query)),
                "country": country,
                "search_lang": search_lang,
            }
        )
        req = request.Request(
            f"{_BRAVE_ENDPOINT}?{params}",
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": api_key,
            },
            method="GET",
        )

        try:
            with request.urlopen(req, timeout=20) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{query}: {exc}")
            continue

        web_results = (payload.get("web") or {}).get("results") or []
        for idx, entry in enumerate(web_results, start=1):
            items.append(
                {
                    "query": query,
                    "rank": idx,
                    "title": entry.get("title") or "",
                    "url": entry.get("url") or "",
                    "snippet": entry.get("description") or "",
                    "age": entry.get("age"),
                    "is_stub": False,
                }
            )

    response: dict[str, Any] = {
        "provider": "brave",
        "configured": True,
        "items": items,
        "message": "ok",
    }
    if errors:
        response["errors"] = errors
    return response


def build_web_evidence(search_output: dict[str, Any], *, note: str | None = None) -> list[EvidenceItem]:
    """Normalize web-search output to persistable EvidenceItem list."""
    retrieved_at = _now_iso()
    items: list[EvidenceItem] = []

    for idx, row in enumerate(search_output.get("items") or [], start=1):
        query = str(row.get("query") or "")
        rank = int(row.get("rank") or idx)
        chunk_id = f"web:{query}:{rank}:{idx}"
        citation_label = f"[web-{idx}]"
        source_url = str(row.get("url") or "about:blank")

        items.append(
            EvidenceItem(
                chunk_id=chunk_id,
                citation_label=citation_label,
                source_url=source_url,
                retrieved_at=retrieved_at,
                note=note or "web_search",
                quote=str(row.get("snippet") or ""),
                metadata={
                    "provider": search_output.get("provider", "brave"),
                    "query": query,
                    "rank": rank,
                    "title": row.get("title"),
                    "age": row.get("age"),
                    "is_stub": bool(row.get("is_stub")),
                },
            )
        )
    return items
