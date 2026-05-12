from app.nexus.research_agent import _retrieval_summary
from app.nexus.web_scout import EngineHealthTracker, resolve_searxng_engines_for_profile


def test_news_profile_uses_google_brave_duckduckgo_when_broad_enabled(monkeypatch):
    monkeypatch.setenv("SEARXNG_ENGINE_PROFILE", "adaptive_broad_research")
    monkeypatch.setenv("NEXUS_ALLOW_BROAD_WEB_ENGINES", "true")
    engines = resolve_searxng_engines_for_profile("news")["searxng_engines"]
    assert engines[:3] == ["google", "brave", "duckduckgo"]


def test_market_profile_uses_google_brave_duckduckgo_when_broad_enabled(monkeypatch):
    monkeypatch.setenv("SEARXNG_ENGINE_PROFILE", "adaptive_broad_research")
    monkeypatch.setenv("NEXUS_ALLOW_BROAD_WEB_ENGINES", "true")
    engines = resolve_searxng_engines_for_profile("market")["searxng_engines"]
    assert engines[:3] == ["google", "brave", "duckduckgo"]
    assert "github" in engines


def test_academic_profile_keeps_academic_engines_first(monkeypatch):
    monkeypatch.setenv("SEARXNG_ENGINE_PROFILE", "adaptive_broad_research")
    monkeypatch.setenv("NEXUS_ALLOW_BROAD_WEB_ENGINES", "true")
    engines = resolve_searxng_engines_for_profile("academic")["searxng_engines"]
    assert engines[:3] == ["arxiv", "crossref", "openalex"]
    assert "google" not in engines[:3]


def test_broad_disabled_reverts_to_safe_mapping(monkeypatch):
    monkeypatch.setenv("NEXUS_ALLOW_BROAD_WEB_ENGINES", "false")
    engines = resolve_searxng_engines_for_profile("source")["searxng_engines"]
    assert engines == ["wikipedia", "wikidata", "arxiv", "crossref", "openalex", "github"]


def test_noisy_non_requested_engines_remain_disabled(monkeypatch):
    monkeypatch.setenv("SEARXNG_ENGINE_PROFILE", "adaptive_broad_research")
    monkeypatch.setenv("NEXUS_ALLOW_BROAD_WEB_ENGINES", "true")
    engines = resolve_searxng_engines_for_profile("news")["searxng_engines"]
    assert "startpage" not in engines
    assert "qwant" not in engines
    assert "mojeek" not in engines
    assert "yahoo" not in engines


def test_captcha_or_403_suspends_engine_for_job():
    tracker = EngineHealthTracker(["google", "brave", "duckduckgo"])
    tracker.record_error("google", "HTTP 403 captcha access denied")
    assert tracker.is_suspended("google")
    filtered, fallback = tracker.filter_engines(["google", "brave", "duckduckgo", "wikipedia"])
    assert "google" not in filtered
    assert fallback is False


def test_all_broad_engines_suspended_falls_back_to_safe_engines():
    tracker = EngineHealthTracker(["google", "brave", "duckduckgo"])
    for engine in ["google", "brave", "duckduckgo"]:
        tracker.record_error(engine, "HTTP 429 Too many requests")
    filtered, fallback = tracker.filter_engines(["google", "brave", "duckduckgo"])
    assert fallback is True
    assert "wikipedia" in filtered
    assert "openalex" in filtered


def test_retrieval_summary_contains_broad_engine_health(monkeypatch):
    monkeypatch.setenv("NEXUS_ALLOW_BROAD_WEB_ENGINES", "true")
    summary = _retrieval_summary(
        targets={},
        retrieval_rounds=[],
        candidate_count=0,
        attempted_download_count=0,
        registered_sources=[],
        evidence_chunks=[],
        skipped_due_to_download_limit_count=0,
        search_policy=resolve_searxng_engines_for_profile("news"),
        engine_health={"suspended_engines": ["google"], "engine_failures": {"google": {"failures": 1}}, "fallback_to_safe_engines": False},
    )
    assert summary["broad_web_enabled"] is True
    assert {"google", "brave", "duckduckgo"}.issubset(set(summary["broad_web_engines"]))
    assert summary["suspended_engines"] == ["google"]
    assert summary["engine_failures"]["google"]["failures"] == 1
