from app.nexus.research_agent import _retrieval_summary
from app.nexus.web_scout import EngineHealthTracker, choose_replacement_engines, get_searxng_engine_status, resolve_searxng_engines_for_profile


def test_default_broad_engines_include_google_bing_brave_duckduckgo(monkeypatch):
    monkeypatch.delenv("NEXUS_BROAD_WEB_ENGINES", raising=False)
    tracker = EngineHealthTracker()
    assert tracker.broad_engines == ["google", "bing", "brave", "duckduckgo"]


def test_default_experimental_engines_include_mojeek(monkeypatch):
    monkeypatch.delenv("NEXUS_EXPERIMENTAL_WEB_ENGINES", raising=False)
    tracker = EngineHealthTracker()
    assert "mojeek" in tracker.experimental_engines


def test_default_disabled_engines_do_not_include_bing_duckduckgo_mojeek(monkeypatch):
    monkeypatch.setenv("SEARXNG_DISABLED_ENGINES", "startpage,karmasearch,karmasearch videos,qwant,yahoo")
    status = get_searxng_engine_status()
    assert not ({"bing", "duckduckgo", "mojeek"} & set(status["disabled_engines"]))


def test_yahoo_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("NEXUS_ENABLE_YAHOO_SEARCH", raising=False)
    assert "yahoo" not in EngineHealthTracker().experimental_engines


def test_yahoo_enabled_only_when_env_true(monkeypatch):
    monkeypatch.setenv("NEXUS_ENABLE_YAHOO_SEARCH", "true")
    assert "yahoo" in EngineHealthTracker().experimental_engines


def test_news_market_source_profiles_include_bing(monkeypatch):
    monkeypatch.setenv("SEARXNG_ENGINE_PROFILE", "adaptive_broad_research")
    monkeypatch.setenv("NEXUS_ALLOW_BROAD_WEB_ENGINES", "true")
    for p in ("news", "market", "source"):
        engines = resolve_searxng_engines_for_profile(p)["searxng_engines"]
        assert engines[:4] == ["google", "bing", "brave", "duckduckgo"]


def test_academic_profile_keeps_academic_engines_first(monkeypatch):
    monkeypatch.setenv("SEARXNG_ENGINE_PROFILE", "adaptive_broad_research")
    engines = resolve_searxng_engines_for_profile("academic")["searxng_engines"]
    assert engines[:3] == ["arxiv", "crossref", "openalex"]


def test_broad_disabled_reverts_to_safe_mapping(monkeypatch):
    monkeypatch.setenv("NEXUS_ALLOW_BROAD_WEB_ENGINES", "false")
    engines = resolve_searxng_engines_for_profile("source")["searxng_engines"]
    assert engines == ["wikipedia", "wikidata", "arxiv", "crossref", "openalex", "github"]


def test_duckduckgo_captcha_suspends_only_current_job():
    t1 = EngineHealthTracker(["google", "bing", "brave", "duckduckgo"])
    t1.record_error("duckduckgo", "captcha")
    assert t1.is_suspended("duckduckgo")
    assert not EngineHealthTracker(["google", "bing", "brave", "duckduckgo"]).is_suspended("duckduckgo")


def test_bing_used_as_replacement_when_google_or_brave_fail():
    engines = choose_replacement_engines("news", "google", {"google", "brave"})
    assert engines[0] == "bing"


def test_mojeek_used_only_as_experimental_fallback(monkeypatch):
    monkeypatch.setenv("NEXUS_EXPERIMENTAL_WEB_ENGINES", "mojeek")
    engines = choose_replacement_engines("news", "duckduckgo", {"google", "bing", "brave", "duckduckgo"})
    assert engines == ["mojeek"]


def test_all_broad_engines_suspended_falls_back_to_safe_engines(monkeypatch):
    monkeypatch.setenv("NEXUS_EXPERIMENTAL_WEB_ENGINES", "")
    engines = choose_replacement_engines("source", None, {"google", "bing", "brave", "duckduckgo"})
    assert "wikipedia" in engines and "arxiv" in engines


def test_web_status_reports_effective_engines_and_warnings(monkeypatch):
    monkeypatch.setenv("SEARXNG_DISABLED_ENGINES", "startpage,google")
    s = get_searxng_engine_status()
    assert s["effective_engines_news"]
    assert s["startup_contract_warning"]


def test_retrieval_summary_contains_broad_engine_health():
    summary = _retrieval_summary(
        targets={}, retrieval_rounds=[], candidate_count=0, attempted_download_count=0,
        registered_sources=[], evidence_chunks=[], skipped_due_to_download_limit_count=0,
        search_policy=resolve_searxng_engines_for_profile("news"),
        engine_health={"experimental_web_engines": ["mojeek"], "disabled_engines": ["yahoo"], "suspended_engines": ["duckduckgo"]},
    )
    assert "experimental_web_engines" in summary
    assert "disabled_engines" in summary
