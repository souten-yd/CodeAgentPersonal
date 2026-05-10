from app.nexus import news_connectors as nc
from app.nexus import news_sources as ns


def _item(title="A", url="https://example.com/a", provider="fake", domain="example.com"):
    return nc.NormalizedNewsItem(
        title=title,
        url=url,
        source_name=domain,
        source_domain=domain,
        provider=provider,
        published_at=None,
        language=None,
        country=None,
        category=None,
        snippet=title,
        image_url=None,
        rights=nc.default_rights("rss"),
        raw={},
        summary=title,
        canonical_url=url,
        source=domain,
        publisher=domain,
        retrieval_method="rss",
        license_note="headline/summary only",
    )


class ItemConnector(nc.BaseNewsConnector):
    provider = "fake_ok"

    def search(self, query):
        return nc.NewsSourceResult(provider=self.provider, query=query, items=[_item(provider=self.provider)], metadata={"endpoint_configured": True})


class EmptyConnector(nc.BaseNewsConnector):
    provider = "fake_empty"

    def search(self, query):
        return nc.NewsSourceResult(provider=self.provider, query=query, metadata={"endpoint_configured": True})


def test_overall_status_empty_provider_status_is_failed():
    assert nc._overall_status([]) == "failed"


def test_overall_status_all_zero_items_is_failed():
    assert nc._overall_status([
        {"provider": "a", "item_count": 0, "error_count": 0, "skipped": False, "endpoint_configured": True},
        {"provider": "b", "item_count": 0, "error_count": 0, "skipped": False, "endpoint_configured": True},
    ]) == "failed"


def test_overall_status_all_skipped_is_failed():
    assert nc._overall_status([
        {"provider": "nhk_rss", "item_count": 0, "error_count": 1, "skipped": True, "endpoint_configured": True},
    ]) == "failed"


def test_overall_status_items_without_provider_problem_is_ok():
    assert nc._overall_status([
        {"provider": "a", "item_count": 1, "error_count": 0, "skipped": False, "endpoint_configured": True},
    ]) == "ok"


def test_overall_status_items_with_searxng_missing_endpoint_is_degraded():
    assert nc._overall_status([
        {"provider": "rss", "item_count": 2, "error_count": 0, "skipped": False, "endpoint_configured": True},
        {"provider": "searxng", "item_count": 0, "error_count": 1, "skipped": False, "endpoint_configured": False},
    ]) == "degraded"


def test_overall_status_items_with_nhk_skipped_is_degraded():
    assert nc._overall_status([
        {"provider": "gdelt", "item_count": 1, "error_count": 0, "skipped": False, "endpoint_configured": True},
        {"provider": "nhk_rss", "item_count": 0, "error_count": 1, "skipped": True, "endpoint_configured": True},
    ]) == "degraded"


def test_provider_status_ok_requires_items_no_errors_no_skip_and_endpoint():
    query = nc.NewsSourceQuery(query="AI", max_items=2)
    result = nc.collect_news_from_connectors(query, providers=["fake_empty"], connectors=[EmptyConnector()])
    status = result["provider_status"][0]
    assert status["errors"] == []
    assert status["ok"] is False
    assert result["overall_status"] == "failed"


def test_collect_news_from_connectors_uses_strict_status_semantics():
    query = nc.NewsSourceQuery(query="AI", max_items=2)
    ok = nc.collect_news_from_connectors(query, providers=["fake_ok"], connectors=[ItemConnector()])
    assert ok["overall_status"] == "ok"

    degraded = nc.collect_news_from_connectors(query, providers=["fake_ok", "searxng"], connectors=[ItemConnector()])
    assert degraded["overall_status"] == "degraded"


def test_collect_news_research_sources_uses_strict_status_semantics(monkeypatch):
    def fake_collect_no_items(query, *, providers=None, max_items=None):
        return {
            "items": [],
            "results": [],
            "provider_status": [{"provider": "empty", "item_count": 0, "error_count": 0, "skipped": False, "endpoint_configured": True}],
            "overall_status": "failed",
            "metadata": {},
        }

    monkeypatch.setattr(ns, "collect_news_from_connectors", fake_collect_no_items)
    profile = ns.NewsResearchSourceProfile(providers=["empty"], max_queries=1, max_items=3)
    failed = ns.collect_news_research_sources("AI", profile=profile)
    assert failed["search"]["overall_status"] == "failed"

    def fake_collect_items_problem(query, *, providers=None, max_items=None):
        return {
            "items": [_item()],
            "results": [],
            "provider_status": [
                {"provider": "rss", "item_count": 1, "error_count": 0, "skipped": False, "endpoint_configured": True},
                {"provider": "searxng", "item_count": 0, "error_count": 1, "skipped": False, "endpoint_configured": False},
            ],
            "overall_status": "degraded",
            "metadata": {},
        }

    monkeypatch.setattr(ns, "collect_news_from_connectors", fake_collect_items_problem)
    degraded = ns.collect_news_research_sources("AI", profile=profile)
    assert degraded["search"]["overall_status"] == "degraded"

    def fake_collect_items_ok(query, *, providers=None, max_items=None):
        return {
            "items": [_item()],
            "results": [],
            "provider_status": [{"provider": "rss", "item_count": 1, "error_count": 0, "skipped": False, "endpoint_configured": True}],
            "overall_status": "ok",
            "metadata": {},
        }

    monkeypatch.setattr(ns, "collect_news_from_connectors", fake_collect_items_ok)
    ok = ns.collect_news_research_sources("AI", profile=profile)
    assert ok["search"]["overall_status"] == "ok"
