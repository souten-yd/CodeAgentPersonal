from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
import uuid

from app.nexus.evidence import EvidenceItem
from app.nexus.news_connectors import (
    DEFAULT_PROVIDERS,
    NewsSourceQuery,
    NormalizedNewsItem,
    collect_news_from_connectors,
)

NewsMode = Literal["quick", "standard", "deep", "exhaustive"]
SourceProfile = Literal["web", "news", "mixed"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class NewsResearchSourceProfile:
    source_profile: SourceProfile = "news"
    providers: list[str] = field(default_factory=lambda: list(DEFAULT_PROVIDERS))
    max_queries: int = 2
    max_items: int = 15
    save_evidence: bool = True
    mode: NewsMode = "standard"
    include_personal_use_only: bool = False


def _normalize_mode(mode: str | None) -> NewsMode:
    return mode if mode in {"quick", "standard", "deep", "exhaustive"} else "standard"  # type: ignore[return-value]


def build_news_research_queries(topic: str, *, profile: NewsResearchSourceProfile) -> list[NewsSourceQuery]:
    seed = (topic or "").strip()
    if not seed:
        raise ValueError("topic is required")
    suffixes = ["latest news", "breaking news", "analysis"] if profile.mode in {"deep", "exhaustive"} else ["latest news", "news"]
    queries: list[NewsSourceQuery] = []
    for suffix in suffixes[: max(1, profile.max_queries)]:
        query_text = seed if suffix.lower() in seed.lower() else f"{seed} {suffix}"
        queries.append(NewsSourceQuery(query=query_text, max_items=profile.max_items, mode=profile.mode))
    return queries


def _item_to_dict(item: NormalizedNewsItem) -> dict[str, Any]:
    return {
        "title": item.title,
        "url": item.url,
        "source_name": item.source_name,
        "source_domain": item.source_domain,
        "provider": item.provider,
        "published_at": item.published_at,
        "language": item.language,
        "country": item.country,
        "category": item.category,
        "snippet": item.snippet,
        "image_url": item.image_url,
        "rights": item.rights,
        "raw": item.raw,
    }


def collect_news_research_sources(topic: str, *, profile: NewsResearchSourceProfile | None = None) -> dict[str, Any]:
    resolved = profile or NewsResearchSourceProfile()
    query_results: list[dict[str, Any]] = []
    items: list[NormalizedNewsItem] = []
    queries = build_news_research_queries(topic, profile=resolved)
    per_query_limit = max(1, resolved.max_items)
    for query in queries:
        collected = collect_news_from_connectors(
            query,
            providers=resolved.providers,
            max_items=per_query_limit,
        )
        filtered = [
            item
            for item in collected["items"]
            if resolved.include_personal_use_only or not bool(item.rights.get("personal_use_only"))
        ]
        items.extend(filtered)
        query_results.append(
            {
                "query": query.query,
                "provider_results": {
                    result.provider: {
                        "count": len(result.items),
                        "errors": result.errors,
                        "items": [_item_to_dict(item) for item in result.items],
                    }
                    for result in collected["results"]
                },
                "metadata": collected["metadata"],
            }
        )
    # Re-run diversity across query union through connector helper semantics.
    seen: set[str] = set()
    merged: list[NormalizedNewsItem] = []
    for item in items:
        key = item.url.lower().rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
        if len(merged) >= resolved.max_items:
            break
    return {
        "source_profile": resolved.source_profile,
        "queries": [query.query for query in queries],
        "items": merged,
        "search": {
            "provider_results": query_results,
            "items": [_item_to_dict(item) for item in merged],
            "retrieved_at": _now_iso(),
            "metadata": {
                "providers": resolved.providers,
                "max_items": resolved.max_items,
                "include_personal_use_only": resolved.include_personal_use_only,
                "save_evidence": resolved.save_evidence,
            },
        },
    }


def convert_news_items_to_evidence(
    items: list[NormalizedNewsItem],
    *,
    topic: str,
    job_kind: str = "news_source_profile",
) -> list[EvidenceItem]:
    evidence: list[EvidenceItem] = []
    retrieved_at = _now_iso()
    for index, item in enumerate(items, start=1):
        source_id = f"news_{uuid.uuid5(uuid.NAMESPACE_URL, item.url).hex}"
        evidence.append(
            EvidenceItem(
                source_id=source_id,
                source_type="news",
                document_id=source_id,
                chunk_id=f"{source_id}:rss_or_search_metadata",
                url=item.url,
                retrieved_at=retrieved_at,
                title=item.title,
                publisher=item.source_name,
                published_date=item.published_at or "",
                relevance_score=0.5,
                credibility_score=0.5,
                freshness_score=0.8,
                evidence_level="news_metadata",
                citation_label=f"[S{index}]",
                note=job_kind,
                quote=item.snippet or item.title,
                metadata_json={
                    "source_type": "news",
                    "topic": topic,
                    "job_kind": job_kind,
                    "provider": item.provider,
                    "source_domain": item.source_domain,
                    "rights": item.rights,
                    "full_text_scraped": False,
                    "raw": item.raw,
                },
            )
        )
    return evidence


def run_news_source_search(
    topic: str,
    *,
    profile: NewsResearchSourceProfile | None = None,
) -> dict[str, Any]:
    resolved = profile or NewsResearchSourceProfile()
    collected = collect_news_research_sources(topic, profile=resolved)
    evidence = convert_news_items_to_evidence(collected["items"], topic=topic)
    return {**collected, "evidence_items": evidence}
