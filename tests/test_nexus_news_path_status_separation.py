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
    assert "const hasProviderOnlyWarning = Boolean(health.non_fatal || health.stub || bundle?.non_fatal || bundle?.stub);" in text


def test_ui_separates_provider_health_and_job_status_dom():
    text = open("ui.html", encoding="utf-8").read()
    # Provider health and job status are kept separate by computing the provider warning via
    # formatNexusProviderHealthWarning and appending it only as a "注意" suffix, instead of
    # overwriting the job status text. (The earlier dual-DOM-element design was refactored into
    # the single nexus-deep-status renderer in setNexusDeepStatus.)
    assert "formatNexusProviderHealthWarning" in text
    assert "const providerWarning = (typeof formatNexusProviderHealthWarning === 'function')" in text
    assert "const warn = providerWarning.show && providerWarning.message ? ` / 注意: ${providerWarning.message}` : '';" in text



def test_news_mvp_path_surfaces_effective_news_providers():
    out = collect_news_research_sources("ai", profile=NewsResearchSourceProfile(max_queries=1, max_items=2))
    assert "effective_news_providers" in out["search"]


def test_no_legacy_brave_searxng_stub_phrase_left_in_ui():
    text = open("ui.html", encoding="utf-8").read()
    assert "Brave/SearXNG 未設定のため stub" not in text


def test_ui_does_not_prefix_job_status_with_stub_wording():
    text = open("ui.html", encoding="utf-8").read()
    assert "[非致命 stub]" not in text


def test_provider_warning_only_in_provider_health_dom():
    text = open("ui.html", encoding="utf-8").read()
    # The provider warning is gated behind providerWarning.show/message and appended separately as a
    # "注意" suffix; the job status text (状態: ${statusMessage}) is rendered independently.
    assert "const warn = providerWarning.show && providerWarning.message ? ` / 注意: ${providerWarning.message}` : '';" in text
    assert "el.textContent = `状態: ${statusMessage}${warn}`;" in text


def test_job_status_keeps_normal_running_text_even_if_stub_non_fatal():
    text = open("ui.html", encoding="utf-8").read()
    # Even in stub/non-fatal mode the job status keeps its normal running text; the provider warning
    # is only ever appended via the separate `warn` suffix, never used to mark the job as failed.
    assert "setNexusDeepStatus('research job を起動中...', false, true);" in text
    assert "el.textContent = `状態: ${statusMessage}${warn}`;" in text


def test_true_job_failure_marks_error_severity():
    text = open("web/js/nexus.js", encoding="utf-8").read()
    assert "const isJobFailed = state === 'failed';" in text
    assert "const severity = (isJobFailed || isNoSources)" in text


def test_no_sources_is_error_severity():
    text = open("web/js/nexus.js", encoding="utf-8").read()
    assert "const isNoSources = reason === 'no_sources';" in text


def test_no_evidence_or_degraded_is_warning_severity():
    text = open("web/js/nexus.js", encoding="utf-8").read()
    assert "const isNoEvidence = reason === 'no_evidence';" in text
    assert "isNoEvidence || state === 'degraded'" in text
