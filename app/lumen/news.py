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
                "source": item.source_name,
                "url": item.url,
                "published_at": item.published_at,
                "snippet": item.snippet,
                "rights": rights,
            }
        )
    for item in items:
        sources.append(
            {
                "name": item.source_name,
                "domain": item.source_domain,
                "provider": item.provider,
                "url": item.url,
                "rights": item.rights,
            }
        )
    retrieved_at = str((collected.get("search") or {}).get("retrieved_at") or _now_iso())
    summary = f"{topic} に関する軽量ニュース digest です。取得件数: {len(items)}。"
    notice = "複数ソースで偏りを下げていますが、完全な中立性は保証しません。"
    if personal_use_only_seen:
        notice += " Yahoo!ニュース RSS など personal_use_only の情報源は個人利用前提で、公開再配信には使えません。"
    return LumenNewsResult(
        ok=True,
        topic=topic,
        summary=summary,
        top_topics=top_topics,
        sources=sources,
        retrieved_at=retrieved_at,
        notice=notice,
        metadata={
            "save_evidence": False,
            "deep_research_started": False,
            "source_profile": "news",
            "queries": collected.get("queries", []),
            "provider_metadata": (collected.get("search") or {}).get("metadata", {}),
            "personal_use_only_seen": personal_use_only_seen,
        },
    )


def compress_news_result_for_llm(result: LumenNewsResult) -> str:
    lines = [result.summary, f"取得時刻: {result.retrieved_at}", "主要トピック:"]
    for idx, item in enumerate(result.top_topics[:5], start=1):
        lines.append(f"{idx}. {item.get('title')} — {item.get('source')} ({item.get('url')})")
    if result.sources:
        source_names = []
        seen = set()
        for source in result.sources:
            key = (source.get("provider"), source.get("domain"))
            if key in seen:
                continue
            seen.add(key)
            source_names.append(f"{source.get('name')}[{source.get('provider')}]")
        lines.append("情報源一覧: " + ", ".join(source_names[:8]))
    lines.append("注意: " + result.notice)
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
