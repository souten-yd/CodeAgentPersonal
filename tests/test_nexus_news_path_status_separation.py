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


def test_web_provider_warning_formatter_does_not_mark_running_job_failed():
    text = open("web/js/nexus.js", encoding="utf-8").read()
    assert "[Web provider warning] Web provider health check is degraded. News/RSS/GDELT sources may still work." in text
    assert "const severity = isHardFailed ? 'error' : (hasNotice ? 'warning' : 'info');" in text


def test_ui_separates_provider_health_and_job_status_dom():
    text = open("ui.html", encoding="utf-8").read()
    assert "id=\"nexus-deep-provider-health\"" in text
    assert "id=\"nexus-deep-job-status\"" in text
    assert "formatNexusProviderHealthWarning" in text


def test_job_failed_no_sources_only_path_is_explicitly_handled():
    text = open("web/js/nexus.js", encoding="utf-8").read()
    assert "const isHardFailed = state === 'failed' && reason === 'no_sources';" in text


def test_news_mvp_path_surfaces_effective_news_providers():
    out = collect_news_research_sources("ai", profile=NewsResearchSourceProfile(max_queries=1, max_items=2))
    assert "effective_news_providers" in out["search"]


def test_no_legacy_brave_searxng_stub_phrase_left_in_ui():
    text = open("ui.html", encoding="utf-8").read()
    assert "Brave/SearXNG 未設定のため stub" not in text
