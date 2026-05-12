from app.nexus.research_agent import _retrieval_summary
from app.nexus.report import _report_section_llm_settings
from app.nexus.source_collector import (
    build_curated_direct_source_candidates,
    build_dynamic_direct_source_candidates,
    collect_source_candidates,
    extract_dynamic_topic_anchors_from_screening,
    rank_source_candidates,
)

SCREENING = [
    {
        "title": "Acme Aerospace Technologies Inc newsroom electric aircraft update",
        "snippet": "Acme electric aircraft battery propulsion market report and investor roadmap.",
        "url": "https://www.acmeaerospace.com/newsroom/electric-aircraft",
    },
    {
        "title": "National aviation agency report",
        "snippet": "Government policy for electric aircraft certification.",
        "url": "https://aviation.gov/reports/electric-aircraft-policy",
    },
]


def test_extracts_entities_and_domains_from_screening_candidates():
    registry = extract_dynamic_topic_anchors_from_screening("electric aircraft market", SCREENING)
    assert "acmeaerospace.com" in registry["domains"]
    assert "aviation.gov" in registry["government_domains"]
    assert any("Acme Aerospace Technologies Inc" in entity for entity in registry["entities"])


def test_builds_dynamic_direct_source_candidates_from_newsroom_ir_report_paths():
    candidates = build_dynamic_direct_source_candidates("electric aircraft market", "market", SCREENING)
    urls = {c["url"] for c in candidates}
    assert "https://acmeaerospace.com/news" in urls or "https://acmeaerospace.com/newsroom" in urls
    assert any("/reports" in url or "/press" in url or "/news" in url for url in urls)
    assert all(c["origin"] == "dynamic_curated_direct_source" for c in candidates)


def test_filters_dynamic_candidates_without_query_anchor_match():
    candidates = build_dynamic_direct_source_candidates("semiconductor lithography", "market", SCREENING)
    assert all("acmeaerospace.com" not in c["url"] for c in candidates)


def test_combines_static_and_dynamic_direct_sources():
    static = build_curated_direct_source_candidates("electric aircraft market", "market")
    dynamic = build_dynamic_direct_source_candidates("electric aircraft market", "market", SCREENING)
    combined = collect_source_candidates(direct_source_candidates=[*static, *dynamic])
    assert any(c["origin"] == "curated_direct_source" for c in combined)
    assert any(c["origin"] == "dynamic_curated_direct_source" for c in combined)


def test_retrieval_summary_contains_dynamic_registry_counts():
    registry = extract_dynamic_topic_anchors_from_screening("electric aircraft market", SCREENING)
    summary = _retrieval_summary(
        targets={},
        retrieval_rounds=[],
        candidate_count=0,
        attempted_download_count=0,
        registered_sources=[],
        evidence_chunks=[],
        skipped_due_to_download_limit_count=0,
        curated_direct_candidate_count=5,
        static_curated_direct_candidate_count=2,
        dynamic_curated_direct_candidate_count=3,
        dynamic_curated_direct_domains=["acmeaerospace.com"],
        dynamic_screening_registry=registry,
    )
    assert summary["static_curated_direct_candidate_count"] == 2
    assert summary["dynamic_curated_direct_candidate_count"] == 3
    assert summary["dynamic_curated_direct_domains"] == ["acmeaerospace.com"]
    assert summary["dynamic_anchor_domains"]


def test_unknown_topic_gets_dynamic_candidates_from_screening():
    candidates = build_dynamic_direct_source_candidates("acme hydrogen avionics market", "market", SCREENING)
    assert candidates


def test_dynamic_candidates_rank_above_generic_safe_search_when_anchor_matches():
    dynamic = build_dynamic_direct_source_candidates("electric aircraft market", "market", SCREENING)[:1]
    generic = [{"url": "https://example.com/page", "title": "generic page", "snippet": "misc", "origin": "search", "relevance_score": 0.4}]
    ranked = rank_source_candidates([*generic, *dynamic], prefer_pdf=False, official_first=True, query="electric aircraft market", source_profile="market")
    assert ranked[0]["origin"] == "dynamic_curated_direct_source"
    assert "dynamic_curated_direct_source_boost" in ranked[0]["quality_reasons"]


def test_deep_enables_section_llm_by_default_when_model_reachable(monkeypatch):
    class Resp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def read(self): return b'{"data": []}'
    monkeypatch.delenv("NEXUS_REPORT_SECTION_LLM_ENABLED", raising=False)
    monkeypatch.setattr("app.nexus.report.request.urlopen", lambda *args, **kwargs: Resp())
    settings = _report_section_llm_settings(depth="deep", retrieval_summary={"depth": "deep"})
    assert settings["enabled"] is True
    assert settings["endpoint"].endswith("/v1/chat/completions")
