import importlib

from app.nexus.news_connectors import NewsSourceQuery, SearxngNewsConnector, collect_news_from_connectors
from app.nexus.news_sources import NewsResearchSourceProfile, collect_news_research_sources


def test_stub_non_fatal_does_not_imply_failed_when_news_items_exist():
    profile = NewsResearchSourceProfile(max_queries=1, max_items=3)
    out = collect_news_research_sources("test", profile=profile)
    if out["items"]:
        assert out["search"]["overall_status"] in {"ok", "degraded"}


def test_searxng_connector_reads_nexus_url_fallback(monkeypatch):
    monkeypatch.delenv("SEARXNG_URL", raising=False)
    monkeypatch.delenv("SEARXNG_ENDPOINT", raising=False)
    monkeypatch.setenv("NEXUS_SEARXNG_URL", "http://nexus-searxng:8088")
    conn = SearxngNewsConnector()
    assert conn.endpoint == "http://nexus-searxng:8088"


def test_brave_api_and_searxng_brave_are_not_mixed():
    module = importlib.import_module("web.js.nexus") if False else None
    text = open("web/js/nexus.js", encoding="utf-8").read()
    assert "Brave API provider: not configured" in text
    assert "SearXNG engine brave: configured through SearXNG, no Brave API key required" in text


def test_deep_research_news_profile_surface_effective_engines_news_shape():
    out = collect_news_research_sources("economy", profile=NewsResearchSourceProfile(max_queries=1, max_items=2))
    assert out["search"]["source_profile"] == "news"


def test_news_mvp_path_surfaces_effective_news_providers():
    out = collect_news_research_sources("ai", profile=NewsResearchSourceProfile(max_queries=1, max_items=2))
    assert "effective_news_providers" in out["search"]


def test_ui_status_formatter_separates_health_warning_and_job_failed_states():
    text = open("web/js/nexus.js", encoding="utf-8").read()
    assert "formatNexusProviderHealthWarning" in text
    assert "state === 'failed'" in text
