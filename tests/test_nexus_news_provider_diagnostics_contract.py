from app.nexus import news_connectors as nc


class EmptyConnector(nc.BaseNewsConnector):
    provider = "empty"

    def search(self, query):
        result = nc.NewsSourceResult(provider=self.provider, query=query, metadata={"endpoint_configured": True})
        return result


def test_provider_status_and_overall_status_are_returned_for_each_provider():
    query = nc.NewsSourceQuery(query="AI", max_items=2)
    result = nc.collect_news_from_connectors(query, providers=["empty", "searxng"], connectors=[EmptyConnector()])
    assert "provider_status" in result
    providers = {status["provider"] for status in result["provider_status"]}
    assert {"empty", "searxng"}.issubset(providers)
    searxng = next(status for status in result["provider_status"] if status["provider"] == "searxng")
    empty = next(status for status in result["provider_status"] if status["provider"] == "empty")
    assert empty["ok"] is False
    assert empty["errors"] == []
    assert searxng["endpoint_configured"] is False
    assert result["overall_status"] == "failed"


def test_provider_status_shape_matches_contract():
    query = nc.NewsSourceQuery(query="AI", max_items=2)
    result = nc.collect_news_from_connectors(query, providers=["nhk_rss"])
    status = result["provider_status"][0]
    for key in ["provider", "ok", "item_count", "error_count", "errors", "skipped", "skip_reason", "endpoint_configured", "retrieved_at"]:
        assert key in status
    assert status["ok"] is False
