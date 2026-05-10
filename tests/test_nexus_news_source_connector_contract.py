from pathlib import Path

from app.nexus import news_connectors as nc


def test_news_connector_module_contract_exists():
    assert Path("app/nexus/news_connectors.py").exists()
    assert nc.NormalizedNewsItem
    assert nc.GdeltDocNewsConnector
    assert nc.SearxngNewsConnector
    assert nc.RssNewsConnector
    assert nc.GoogleNewsRssConnector


def test_no_key_default_and_full_text_default_false():
    assert nc.DEFAULT_PROVIDERS == ["google_news_rss", "nhk_rss", "yahoo_rss", "cnbc_rss", "bbc_rss", "gdelt", "searxng"]
    assert nc.API_KEY_REQUIRED_PROVIDERS.isdisjoint(nc.DEFAULT_PROVIDERS)
    assert nc.default_rights("rss")["full_text_allowed"] is False


def test_yahoo_rss_personal_use_only_and_cnbc_not_redistributable():
    feeds = nc.load_rss_feed_configs()
    yahoo = next(feed for feed in feeds if "Yahoo" in feed["name"])
    cnbc = next(feed for feed in feeds if "CNBC" in feed["name"])
    assert yahoo["personal_use_only"] is True
    assert yahoo["allow_public_redistribution"] is False
    assert yahoo["full_text_allowed"] is False
    assert cnbc["personal_use_only"] is False
    assert cnbc["allow_public_redistribution"] is False
    assert cnbc["full_text_allowed"] is False


def test_source_domain_dedupe_and_provider_diversity_limit():
    rights = nc.default_rights("rss")
    items = [
        nc.NormalizedNewsItem("Same Title", "https://a.example/x?utm_source=1", "A", "a.example", "rss", None, None, None, None, None, None, rights, {}),
        nc.NormalizedNewsItem("Same Title", "https://a.example/x", "A", "a.example", "rss", None, None, None, None, None, None, rights, {}),
        nc.NormalizedNewsItem("Other", "https://b.example/y", "B", "b.example", "gdelt", None, None, None, None, None, None, rights, {}),
        nc.NormalizedNewsItem("Third", "https://c.example/z", "C", "c.example", "gdelt", None, None, None, None, None, None, rights, {}),
    ]
    assert len(nc.dedupe_news_items(items)) == 3
    selected, metadata = nc.apply_news_source_diversity(nc.dedupe_news_items(items), max_items=3)
    assert metadata["provider_cap"] == 2
    assert metadata["domain_cap"] >= 1
    assert len(selected) <= 3
