from datetime import datetime, timezone
from urllib.parse import urlparse

from app.nexus.research_agent import _retrieval_summary
from app.nexus.source_collector import (
    build_curated_direct_source_candidates,
    collect_source_candidates,
    get_curated_domain_hints,
    rank_source_candidates,
)


def _domains(candidates: list[dict]) -> set[str]:
    return {urlparse(str(item.get("url") or "")).netloc.lower() for item in candidates}


def test_market_profile_adds_curated_direct_candidates():
    candidates = build_curated_direct_source_candidates("航空機電動化の市場動向", "market")
    assert candidates
    pool = collect_source_candidates(search_items=[], direct_source_candidates=candidates)
    assert any(item["origin"] == "curated_direct_source" for item in pool)
    assert len(pool) == len(candidates)


def test_aviation_market_adds_airbus_boeing_nasa_faa_candidates():
    candidates = build_curated_direct_source_candidates("航空機電動化 electric aircraft eVTOL market", "market")
    domains = _domains(candidates)
    assert "www.nasa.gov" in domains
    assert "www.faa.gov" in domains
    assert "www.airbus.com" in domains
    assert "www.boeing.com" in domains
    assert "www.geaerospace.com" in domains
    assert "www.rolls-royce.com" in domains


def test_semiconductor_market_adds_meti_nedo_semi_company_candidates():
    candidates = build_curated_direct_source_candidates("次世代 半導体 SiC GaN market outlook", "market")
    urls = "\n".join(item["url"] for item in candidates)
    assert "meti.go.jp" in urls
    assert "nedo.go.jp" in urls
    assert "semi.org" in urls
    assert "semiconductors.org" in urls
    assert "infineon.com" in urls
    assert "onsemi.com" in urls
    assert "rohm.com" in urls
    assert "st.com" in urls
    assert "toshiba.semicon-storage.com" in urls


def test_curated_candidates_have_source_type_and_reason():
    candidates = build_curated_direct_source_candidates("semiconductor market latest", "news")
    assert candidates
    for candidate in candidates:
        assert candidate["source_type_hint"] in {
            "company_newsroom",
            "press_release",
            "investor_relations",
            "annual_report",
            "industry_association",
            "government_agency",
            "market_report",
        }
        assert candidate["curated_reason"]
        assert candidate["expected_freshness"]
        assert candidate["metadata"]["curated_direct_source"] is True


def test_unrelated_curated_candidates_are_filtered_by_topic_anchor():
    unrelated = build_curated_direct_source_candidates("半導体 market", "market")
    ranked = rank_source_candidates(
        unrelated,
        prefer_pdf=False,
        official_first=True,
        now=datetime(2026, 5, 12, tzinfo=timezone.utc),
        query="航空機電動化 electric aircraft market",
        source_profile="market",
    )
    assert ranked == []


def test_retrieval_summary_contains_curated_direct_counts():
    summary = _retrieval_summary(
        targets={},
        retrieval_rounds=[],
        candidate_count=3,
        attempted_download_count=2,
        registered_sources=[{"url": "https://www.nasa.gov/aeronautics/", "status": "downloaded", "origin": "curated_direct_source"}],
        evidence_chunks=[],
        skipped_due_to_download_limit_count=0,
        curated_direct_candidate_count=4,
        curated_direct_downloaded_count=1,
        curated_direct_domains=["www.nasa.gov", "www.faa.gov"],
        search_policy={"source_profile": "market", "engine_priority": "profile_safe", "searxng_engines": ["wikipedia"], "freshness_policy": "prioritize_last_12_months"},
    )
    assert summary["curated_direct_candidate_count"] == 4
    assert summary["curated_direct_downloaded_count"] == 1
    assert summary["curated_direct_domains"] == ["www.nasa.gov", "www.faa.gov"]


def test_get_curated_domain_hints_can_return_url_candidates():
    hints = get_curated_domain_hints("航空機電動化 electric aircraft", "source", include_url_candidates=True)
    assert "domain_hints" in hints
    assert "url_candidates" in hints
    assert any("airbus.com/en/newsroom" in url for url in hints["url_candidates"])
