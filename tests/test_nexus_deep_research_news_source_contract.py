from app.nexus.news import run_news_mvp
from app.nexus.news_sources import (
    NewsResearchSourceProfile,
    collect_news_research_sources,
    convert_news_items_to_evidence,
)
from app.nexus.research_agent import ResearchAgentInput


def test_news_research_source_profile_contract():
    profile = NewsResearchSourceProfile(source_profile="news", save_evidence=True)
    assert profile.source_profile == "news"
    assert profile.save_evidence is True
    mixed = NewsResearchSourceProfile(source_profile="mixed")
    assert mixed.source_profile == "mixed"


def test_news_source_functions_exist():
    assert collect_news_research_sources
    assert convert_news_items_to_evidence


def test_research_agent_source_profile_payloads():
    news_payload = ResearchAgentInput(query="AI", source_profile="news", news_budget={"max_total_items": 3})
    mixed_payload = ResearchAgentInput(query="AI", source_profile="mixed")
    assert news_payload.source_profile == "news"
    assert mixed_payload.source_profile == "mixed"
    assert news_payload.news_budget["max_total_items"] == 3


def test_nexus_and_lumen_save_evidence_modes():
    nexus = NewsResearchSourceProfile(source_profile="news", save_evidence=True, include_personal_use_only=False)
    lumen = NewsResearchSourceProfile(source_profile="news", save_evidence=False, include_personal_use_only=True)
    assert nexus.save_evidence is True
    assert lumen.save_evidence is False


def test_run_news_mvp_uses_news_source_layer():
    names = set(run_news_mvp.__code__.co_names)
    assert "NewsResearchSourceProfile" in names
    assert "collect_news_research_sources" in names
    assert "convert_news_items_to_evidence" in names


def test_run_news_mvp_preserves_news_search_metadata(monkeypatch):
    from types import SimpleNamespace
    from app.nexus import news as news_module

    search = {
        "provider_status": [{"provider": "rss", "item_count": 1, "error_count": 0, "skipped": False, "endpoint_configured": True}],
        "overall_status": "ok",
        "metadata": {
            "final_diversity": {"provider_counts": {"rss": 1}},
            "deduped_union_count": 1,
            "evidence_metadata": {"full_text_scraped": False},
        },
    }
    monkeypatch.setattr(news_module, "load_runtime_config", lambda: SimpleNamespace(enable_news=True))
    monkeypatch.setattr(news_module, "create_job", lambda *args, **kwargs: None)
    monkeypatch.setattr(news_module, "update_job", lambda *args, **kwargs: None)
    monkeypatch.setattr(news_module, "save_evidence_items", lambda *args, **kwargs: 0)
    monkeypatch.setattr(news_module, "convert_news_items_to_evidence", lambda *args, **kwargs: [])
    monkeypatch.setattr(news_module, "collect_news_research_sources", lambda *args, **kwargs: {"items": [], "queries": ["AI news"], "search": search})

    result = run_news_mvp("AI")
    metadata = result["search"]["metadata"]
    assert result["search"]["overall_status"] in {"ok", "degraded", "failed"}
    assert result["search"]["provider_status"]
    assert metadata["final_diversity"]
    assert metadata["deduped_union_count"] == 1
    assert metadata["evidence_metadata"]["full_text_scraped"] is False


def test_news_source_search_metadata_contains_runtime_diagnostics(monkeypatch):
    from app.nexus import news_sources as ns
    from app.nexus import news_connectors as nc

    item = nc.NormalizedNewsItem(
        "Title",
        "https://example.com/title",
        "Example",
        "example.com",
        "rss",
        None,
        None,
        None,
        None,
        "Summary",
        None,
        nc.default_rights("rss"),
        {},
        summary="Summary",
        canonical_url="https://example.com/title",
        source="Example",
        publisher="Example",
        retrieval_method="rss",
        license_note="headline/summary only",
    )

    def fake_collect(query, *, providers=None, max_items=None):
        return {
            "items": [item],
            "results": [],
            "provider_status": [{"provider": "rss", "item_count": 1, "error_count": 0, "skipped": False, "endpoint_configured": True}],
            "overall_status": "ok",
            "metadata": {},
        }

    monkeypatch.setattr(ns, "collect_news_from_connectors", fake_collect)
    result = ns.collect_news_research_sources("AI", profile=ns.NewsResearchSourceProfile(providers=["rss"], max_queries=1, max_items=3))
    metadata = result["search"]["metadata"]
    assert result["search"]["overall_status"] in {"ok", "degraded", "failed"}
    assert metadata["provider_status"]
    assert metadata["final_diversity"]
    assert metadata["deduped_union_count"] == 1
    assert metadata["evidence_metadata"]["full_text_scraped"] is False
