from datetime import datetime, timezone

from app.nexus.research_agent import _retrieval_summary
from app.nexus.research_planner import build_focused_research_plan, infer_research_intent
from app.nexus.source_collector import rank_source_candidates
from app.nexus.web_scout import plan_web_queries, resolve_searxng_engines_for_profile


NOISY = {"duckduckgo", "startpage", "google", "bing", "brave", "karmasearch", "yahoo", "qwant", "mojeek"}


def test_academic_profile_uses_academic_engines(monkeypatch):
    monkeypatch.delenv("NEXUS_SEARXNG_ENGINES", raising=False)
    monkeypatch.delenv("NEXUS_SEARXNG_ENGINES_ACADEMIC", raising=False)
    resolved = resolve_searxng_engines_for_profile("academic", "deep", "balanced")
    assert {"arxiv", "crossref", "openalex", "semantic scholar"}.issubset(set(resolved["searxng_engines"]))
    assert resolved["source_profile"] == "academic"


def test_news_profile_does_not_use_noisy_engines_by_default(monkeypatch):
    monkeypatch.setenv("NEXUS_SEARXNG_ENGINES_NEWS", "wikipedia,duckduckgo,bing,wikidata")
    monkeypatch.delenv("NEXUS_ALLOW_BROAD_UNSAFE_SEARCH", raising=False)
    resolved = resolve_searxng_engines_for_profile("news", "deep", "recent")
    assert not (set(resolved["searxng_engines"]) & NOISY)
    assert resolved["freshness_policy"] == "prioritize_last_12_months"


def test_market_profile_uses_freshness_queries():
    queries = plan_web_queries("AI chips", mode="deep", max_queries=12, source_profile="market")
    joined = " ".join(queries).lower()
    assert "market size" in joined
    assert "cagr" in joined
    assert "forecast" in joined
    assert "investment" in joined
    assert "market outlook" in joined


def test_official_profile_uses_site_and_pdf_queries():
    queries = plan_web_queries("battery policy", mode="deep", max_queries=12, source_profile="official")
    joined = " ".join(queries).lower()
    assert "site:.gov" in joined or "site:go.jp" in joined
    assert "pdf" in joined
    assert "official" in joined


def test_source_profile_uses_pdf_report_ir_queries():
    queries = plan_web_queries("robotics", mode="deep", max_queries=12, source_profile="source")
    joined = " ".join(queries).lower()
    assert "pdf report" in joined
    assert "white paper" in joined
    assert "annual report" in joined
    assert "investor relations" in joined


def test_freshness_score_boosts_recent_news_market_sources():
    now = datetime(2026, 5, 12, tzinfo=timezone.utc)
    ranked = rank_source_candidates(
        [
            {"url": "https://example.com/old", "title": "market outlook", "published_at": "2021-01-01T00:00:00+00:00", "relevance_score": 0.8},
            {"url": "https://example.com/new", "title": "market outlook", "published_at": "2026-04-15T00:00:00+00:00", "relevance_score": 0.8},
        ],
        prefer_pdf=False,
        official_first=False,
        now=now,
        query="market outlook",
        source_profile="market",
    )
    assert ranked[0]["url"].endswith("/new")
    assert ranked[0]["freshness_score"] > ranked[1]["freshness_score"]
    assert "recent_news_market_boost" in ranked[0]["quality_reasons"]


def test_retrieval_summary_contains_engine_priority_and_freshness_policy():
    intent = infer_research_intent("AI market latest", "market", "deep")
    summary = _retrieval_summary(
        targets={},
        retrieval_rounds=[],
        candidate_count=2,
        attempted_download_count=2,
        registered_sources=[
            {"url": "https://example.com/a", "status": "downloaded", "freshness_bucket": "fresh", "freshness_score": 1.0},
            {"url": "https://example.com/b", "status": "downloaded", "freshness_bucket": "stale", "freshness_score": -0.1},
        ],
        evidence_chunks=[],
        skipped_due_to_download_limit_count=0,
        intent=intent,
        focused_research_plan=build_focused_research_plan(intent, {}, depth="deep"),
    )
    assert summary["source_profile"] == "market"
    assert summary["engine_priority"]
    assert summary["searxng_engines"]
    assert summary["freshness_policy"]
    assert summary["fresh_source_count"] == 1
    assert summary["stale_source_count"] == 1
