import json
from pathlib import Path

from app.nexus import news_connectors as nc


def test_rss_feed_config_has_profiles_and_default_order():
    data = json.loads(Path("config/lumen/rss_feeds.json").read_text(encoding="utf-8"))
    assert "profiles" in data
    assert data["profiles"]["default"] == [
        "google_news_rss",
        "nhk_rss",
        "yahoo_rss",
        "cnbc_rss",
        "bbc_rss",
        "gdelt",
        "searxng",
    ]
    assert nc.resolve_news_provider_profile("default") == data["profiles"]["default"]


def test_google_news_rss_connector_exists_and_is_aggregator():
    assert nc.GoogleNewsRssConnector
    connector = nc.GoogleNewsRssConnector()
    assert connector.provider == "google_news_rss"
    assert connector.feed.retrieval_method == "rss"
    assert "aggregator" in connector.feed.license_note


def test_nhk_unvalidated_feed_is_skipped_degraded():
    query = nc.NewsSourceQuery(query="AI", max_items=2)
    result = nc.collect_news_from_connectors(query, providers=["nhk_rss"], max_items=2)
    status = result["provider_status"][0]
    assert status["provider"] == "nhk_rss"
    assert status["skipped"] is True
    assert status["error_count"] >= 1
    assert result["overall_status"] == "degraded"


def test_yahoo_cnbc_bbc_rss_rights_metadata():
    feeds = nc.load_rss_feed_configs()
    yahoo = next(feed for feed in feeds if feed["id"] == "yahoo_rss_top")
    cnbc = next(feed for feed in feeds if feed["id"] == "cnbc_rss")
    bbc = next(feed for feed in feeds if feed["id"] == "bbc_rss")
    assert yahoo["personal_use_only"] is True
    assert yahoo["allow_public_redistribution"] is False
    assert yahoo["full_text_allowed"] is False
    assert cnbc["retrieval_method"] == "rss"
    assert bbc["retrieval_method"] == "rss"
