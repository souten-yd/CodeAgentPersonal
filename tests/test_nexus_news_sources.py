from app.nexus.news_sources import NewsResearchSourceProfile, collect_news_research_sources


def test_collect_news_sources_exposes_provider_status_fields():
    out = collect_news_research_sources("market", profile=NewsResearchSourceProfile(max_queries=1, max_items=3))
    assert "provider_status" in out["search"]
    assert "effective_news_providers" in out["search"]
