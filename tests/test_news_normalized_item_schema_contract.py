from app.nexus import news_connectors as nc
from app.nexus.news_sources import convert_news_items_to_evidence


def test_normalized_news_item_schema_has_rss_first_fields():
    fields = nc.NormalizedNewsItem.__dataclass_fields__
    for name in ["summary", "canonical_url", "source", "publisher", "fetched_at", "retrieval_method", "license_note"]:
        assert name in fields


def test_evidence_metadata_preserves_canonical_source_and_rights():
    rights = nc.default_rights("rss", note="headline/summary only")
    item = nc.NormalizedNewsItem(
        "Title",
        "https://news.google.com/rss/articles/x",
        "Google News",
        "example.com",
        "google_news_rss",
        "2026-05-10",
        "en",
        "US",
        "business",
        "Summary",
        None,
        rights,
        {"raw": True},
        summary="Summary",
        canonical_url="https://example.com/story",
        source="Google News",
        publisher="Example Publisher",
        retrieval_method="rss",
        license_note="aggregator headline/summary only",
    )
    evidence = convert_news_items_to_evidence([item], topic="AI", job_kind="test")
    metadata = evidence[0].metadata_json
    assert metadata["canonical_url"] == "https://example.com/story"
    assert metadata["publisher"] == "Example Publisher"
    assert metadata["retrieval_method"] == "rss"
    assert metadata["license_note"] == "aggregator headline/summary only"
    assert metadata["full_text_scraped"] is False
    assert evidence[0].quote == "Summary"
