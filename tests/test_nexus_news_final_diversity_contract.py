from app.nexus import news_sources as ns
from app.nexus import news_connectors as nc


def _item(title, url, provider, domain):
    return nc.NormalizedNewsItem(
        title,
        url,
        domain,
        domain,
        provider,
        None,
        None,
        None,
        None,
        title,
        None,
        nc.default_rights("rss"),
        {},
        summary=title,
        canonical_url=url,
        source=domain,
        publisher=domain,
        retrieval_method="rss",
        license_note="headline/summary only",
    )


def test_collect_news_research_sources_reapplies_final_diversity(monkeypatch):
    items = [
        _item(f"A{i}", f"https://a.example/{i}", "google_news_rss", "a.example") for i in range(8)
    ] + [
        _item("B", "https://b.example/1", "cnbc_rss", "b.example"),
        _item("C", "https://c.example/1", "bbc_rss", "c.example"),
    ]

    def fake_collect(query, *, providers=None, max_items=None):
        return {
            "items": items,
            "results": [],
            "provider_status": [{"provider": "fake", "error_count": 0, "skipped": False, "endpoint_configured": True, "item_count": len(items)}],
            "overall_status": "ok",
            "metadata": {},
        }

    monkeypatch.setattr(ns, "collect_news_from_connectors", fake_collect)
    profile = ns.NewsResearchSourceProfile(max_queries=2, max_items=5)
    collected = ns.collect_news_research_sources("AI", profile=profile)
    final = collected["search"]["metadata"]["final_diversity"]
    assert len(collected["items"]) <= 5
    assert final["provider_counts"]["google_news_rss"] <= final["provider_cap"]
    assert collected["search"]["overall_status"] in {"ok", "degraded", "failed"}
    assert collected["search"]["metadata"]["deduped_union_count"] >= len(collected["items"])
    assert collected["search"]["metadata"]["evidence_metadata"]["full_text_scraped"] is False
