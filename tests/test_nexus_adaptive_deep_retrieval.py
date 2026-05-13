from pathlib import Path

from app.nexus.answer_builder import build_answer_payload
from app.nexus.report import build_report
from app.nexus.research_agent import (
    ResearchAgentInput,
    build_retrieval_strategy,
    build_retrieval_targets,
    should_expand_retrieval,
)
from app.nexus.source_collector import get_curated_domain_hints, rank_source_candidates


def test_deep_targets_are_larger_than_standard():
    standard = build_retrieval_targets(ResearchAgentInput(query="q", mode="standard", depth="standard"))
    deep = build_retrieval_targets(ResearchAgentInput(query="q", mode="deep", depth="deep"))
    exhaustive = build_retrieval_targets(ResearchAgentInput(query="q", mode="exhaustive", depth="exhaustive"))

    assert deep["target_valid_source_count"] >= 35
    assert deep["target_evidence_count"] >= 100
    assert exhaustive["target_valid_source_count"] >= 55
    assert deep["target_valid_source_count"] > standard["target_valid_source_count"]


def test_should_expand_when_valid_sources_below_target():
    expand, reasons = should_expand_retrieval(
        {"valid_source_count": 3, "evidence_count": 100, "candidate_count": 100},
        {"target_valid_source_count": 8, "target_evidence_count": 10, "target_candidate_count": 10, "max_retrieval_rounds": 3},
        1,
    )
    assert expand is True
    assert "valid_sources_below_target" in reasons


def test_should_not_expand_when_targets_satisfied():
    expand, reasons = should_expand_retrieval(
        {"valid_source_count": 8, "evidence_count": 25, "candidate_count": 30},
        {"target_valid_source_count": 8, "target_evidence_count": 25, "target_candidate_count": 30, "max_retrieval_rounds": 3},
        1,
    )
    assert expand is False
    assert reasons == []


def test_retrieval_rounds_emit_events():
    text = Path("app/nexus/research_agent.py").read_text(encoding="utf-8")
    assert "retrieval_round_started" in text
    assert "retrieval_round_completed" in text


def test_adaptive_strategy_includes_official_pdf_report_round():
    strategy = build_retrieval_strategy("market", "deep", 1)
    variants = " ".join(strategy["query_suffixes"])
    assert strategy["name"] == "official_pdf_report"
    assert "PDF" in variants
    assert "report" in variants
    assert "official" in variants


def test_curated_domain_hints_for_aviation():
    hints = get_curated_domain_hints("航空機電動化 electric aircraft eVTOL market", "market")
    joined = " ".join(hints).lower()
    for expected in ["nasa.gov", "faa.gov", "easa.europa.eu", "icao.int", "iata.org", "airbus.com"]:
        assert expected in joined


def test_candidate_pool_separate_from_downloads():
    targets = build_retrieval_targets(
        ResearchAgentInput(query="q", depth="deep", max_sources=100, max_downloads=48)
    )
    summary = {
        "candidate_count": 100,
        "attempted_download_count": 48,
        "skipped_due_to_download_limit_count": 52,
        "valid_source_count": targets["target_valid_source_count"],
        "evidence_count": targets["target_evidence_count"],
        "high_quality_source_count": targets["target_high_quality_source_count"],
        "official_source_count": targets["target_official_source_count"],
        "pdf_source_count": targets["target_pdf_source_count"],
    }
    expand, reasons = should_expand_retrieval(summary, {**targets, "target_candidate_count": 100}, 1)
    assert summary["attempted_download_count"] < summary["candidate_count"]
    assert "skipped_download_limit" not in reasons
    assert expand is False


def test_candidate_scoring_sets_retrieval_score_and_quality_reasons():
    ranked = rank_source_candidates(
        [{"url": "https://nasa.gov/report.pdf", "title": "Electric aircraft market report", "snippet": "official PDF report", "relevance_score": 0.8}],
        prefer_pdf=True,
        official_first=True,
        query="electric aircraft market",
        trusted_domain_hints=["nasa.gov"],
    )
    assert ranked[0]["retrieval_score"] > 0
    assert "official_domain" in ranked[0]["quality_reasons"]
    assert "pdf" in ranked[0]["quality_reasons"]


def test_retrieval_summary_in_answer_json(monkeypatch):
    monkeypatch.setenv("DEEP_RESEARCH_LLM_ENABLED", "0")
    payload = build_answer_payload(
        question="q",
        references=[],
        retrieval_summary={"target_candidate_count": 180, "retrieval_rounds": [{"round": 1}], "targets_satisfied": False},
    )
    assert payload["retrieval_summary"]["target_candidate_count"] == 180
    assert payload["retrieval_summary"]["retrieval_rounds"][0]["round"] == 1


def test_report_includes_retrieval_scope(tmp_path, monkeypatch):
    monkeypatch.setattr("app.nexus.report.REPORTS_DIR", tmp_path)
    report = build_report(
        "job-adaptive",
        "general",
        "Adaptive Report",
        [{"heading": "調査範囲", "summary": "候補件数=180 / Evidence件数=100", "evidence": []}],
        metadata={"retrieval_summary": {"candidate_count": 180, "valid_source_count": 35, "evidence_count": 100}},
    )
    assert "retrieval_summary" in report["metadata"]
    assert "調査範囲" in Path(report["markdown_path"]).read_text(encoding="utf-8")


def test_deep_targets_include_replenishment_budget():
    deep = build_retrieval_targets(ResearchAgentInput(query="q", mode="deep", depth="deep"))
    exhaustive = build_retrieval_targets(ResearchAgentInput(query="q", mode="exhaustive", depth="exhaustive"))
    assert deep["max_replenishment_rounds"] == 3
    assert deep["max_replenishment_candidates"] == 120
    assert exhaustive["max_replenishment_rounds"] == 5
    assert exhaustive["max_replenishment_candidates"] == 220
