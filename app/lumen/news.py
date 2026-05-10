from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.lumen.budgets import LumenNewsBudget, clamp_lumen_news_budget
from app.nexus.news_sources import NewsResearchSourceProfile, collect_news_research_sources


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class LumenNewsRequest(BaseModel):
    message: str = ""
    topic: str | None = None
    budget: LumenNewsBudget = Field(default_factory=LumenNewsBudget)
    include_personal_use_only: bool = True


class LumenNewsResult(BaseModel):
    ok: bool = False
    topic: str = ""
    summary: str = ""
    top_topics: list[dict[str, Any]] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    retrieved_at: str = ""
    notice: str = "複数ソースで偏りを下げていますが、完全な中立性は保証しません。"
    metadata: dict[str, Any] = Field(default_factory=dict)


def _infer_topic(message: str, explicit: str | None = None) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    text = (message or "").strip()
    for marker in ("について", "を", "の"):
        if marker in text:
            candidate = text.split(marker)[0].strip()
            if candidate and len(candidate) <= 80:
                return candidate
    return text or "latest news"


def run_lumen_news_tool(request: LumenNewsRequest) -> LumenNewsResult:
    """Run lightweight news digest only; never save Nexus evidence or start Deep Research."""

    budget = clamp_lumen_news_budget(request.budget)
    topic = _infer_topic(request.message, request.topic)
    profile = NewsResearchSourceProfile(
        source_profile="news",
        max_queries=budget.max_queries,
        max_items=budget.max_total_items,
        save_evidence=False,  # Lumen digest does not save evidence.
        mode="quick",
        include_personal_use_only=request.include_personal_use_only,
    )
    profile.providers = profile.providers[: budget.max_providers]
    collected = collect_news_research_sources(topic, profile=profile)
    items = collected.get("items") or []
    top_topics = []
    sources = []
    personal_use_only_seen = False
    for item in items[:5]:
        rights = dict(item.rights or {})
        personal_use_only_seen = personal_use_only_seen or bool(rights.get("personal_use_only"))
        top_topics.append(
            {
                "title": item.title,
                "source": item.source,
                "publisher": item.publisher,
                "url": item.url,
                "canonical_url": item.canonical_url,
                "published_at": item.published_at,
                "summary": item.summary,
                "snippet": item.snippet,
                "retrieval_method": item.retrieval_method,
                "license_note": item.license_note,
                "rights": rights,
            }
        )
    for item in items:
        sources.append(
            {
                "name": item.source,
                "publisher": item.publisher,
                "domain": item.source_domain,
                "provider": item.provider,
                "url": item.url,
                "canonical_url": item.canonical_url,
                "retrieval_method": item.retrieval_method,
                "rights": item.rights,
            }
        )
    search = collected.get("search") or {}
    provider_metadata = search.get("metadata") or {}
    overall_status = str(search.get("overall_status") or "failed")
    final_diversity = provider_metadata.get("final_diversity") or {}
    provider_status = search.get("provider_status") or []
    retrieved_at = str(search.get("retrieved_at") or _now_iso())
    summary = f"{topic} に関する軽量ニュース digest です。取得件数: {len(items)}。"
    notice = "複数ソースで偏りを下げていますが、完全な中立性は保証しません。"
    if personal_use_only_seen:
        notice += " Yahoo!ニュース RSS など personal_use_only の情報源は個人利用前提で、公開再配信には使えません。"
    return LumenNewsResult(
        ok=overall_status != "failed",
        topic=topic,
        summary=summary,
        top_topics=top_topics,
        sources=sources,
        retrieved_at=retrieved_at,
        notice=notice,
        metadata={
            "overall_status": overall_status,
            "provider_status": provider_status,
            "final_diversity": final_diversity,
            "item_count": len(items),
            "save_evidence": False,
            "deep_research_started": False,
            "source_profile": "news",
            "queries": collected.get("queries", []),
            "provider_metadata": provider_metadata,
            "personal_use_only_seen": personal_use_only_seen,
        },
    )


def _provider_status_summary(provider_status: list[dict[str, Any]]) -> str:
    parts = []
    for status in provider_status[:8]:
        state = "ok" if status.get("ok") else ("skipped" if status.get("skipped") else "failed")
        if not status.get("endpoint_configured", True):
            state = "endpoint_missing"
        parts.append(f"{status.get('provider')}={state}:{status.get('item_count', 0)}")
    return ", ".join(parts)


def compress_news_result_for_llm(result: LumenNewsResult) -> str:
    provider_status = result.metadata.get("provider_status") or []
    if result.metadata.get("overall_status") == "failed":
        lines = [
            "ニュースソースから有効な記事を取得できませんでした。",
            "推測でニュース本文や見出しを作らず、取得失敗として回答してください。",
            f"item_count={result.metadata.get('item_count', len(result.top_topics))}",
        ]
        if provider_status:
            lines.append("provider status: " + _provider_status_summary(provider_status))
        return "\n".join(lines).strip()

    lines = ["要約: " + result.summary, f"retrieved_at: {result.retrieved_at}", "主要トピック:"]
    for idx, item in enumerate(result.top_topics[:5], start=1):
        publisher = item.get("publisher") or item.get("source")
        via = "（Google News経由）" if item.get("source") == "Google News" else ""
        lines.append(f"{idx}. {item.get('title')} — {item.get('source')}/{publisher}{via}")
        lines.append(f"   url: {item.get('url')}")
        if item.get("canonical_url"):
            lines.append(f"   canonical_url: {item.get('canonical_url')}")
    if provider_status:
        lines.append("provider status: " + _provider_status_summary(provider_status))
    if result.sources:
        source_names = []
        seen = set()
        for source in result.sources:
            key = (source.get("provider"), source.get("domain"))
            if key in seen:
                continue
            seen.add(key)
            source_names.append(f"{source.get('name')}/{source.get('publisher')}[{source.get('provider')}]")
        lines.append("情報源一覧: " + ", ".join(source_names[:8]))
    lines.append("注意: headline/summary only; full text not fetched; multiple sources reduce bias but do not guarantee neutrality. " + result.notice)
    return "\n".join(lines).strip()


def build_nexus_news_handoff(message: str, *, project: str = "default", mode: str = "standard", news_budget: dict[str, Any] | None = None) -> dict[str, Any]:
    topic = _infer_topic(message)
    budget = news_budget or {"max_providers": 3, "max_total_items": 15}
    return {
        "handoff": "nexus_deep_research",
        "message": "NexusでNews Deep Researchを実行できます。Lumenからは自動起動しません。",
        "auto_started": False,
        "payload": {
            "project": project,
            "query": topic,
            "mode": mode,
            "source_profile": "news",
            "news_budget": budget,
        },
    }
