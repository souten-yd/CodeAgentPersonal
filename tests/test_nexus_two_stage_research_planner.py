from app.nexus.answer_builder import build_answer_payload
from app.nexus.research_planner import (
    build_coverage_matrix,
    build_focused_research_plan,
    build_report_outline,
    get_screening_settings,
    infer_research_intent,
    summarize_screening_candidates,
)


def test_deep_enables_broad_screening():
    settings = get_screening_settings("deep")
    assert settings["enabled"] is True
    assert settings["target_screening_candidates"] >= 200
    assert settings["max_screening_queries"] >= 12


def test_standard_does_not_force_large_screening():
    settings = get_screening_settings("standard")
    assert settings["enabled"] is False or settings["target_screening_candidates"] <= 60


def test_infer_market_intent_from_query():
    intent = infer_research_intent("航空機電動化の市場動向", None, "deep")
    assert intent["expected_output_type"] == "market_analysis"
    assert intent["source_profile"] == "market"


def test_screening_summary_counts_domains_and_source_types():
    candidates = [
        {"url": "https://nasa.gov/a.pdf", "title": "official electric aircraft report", "snippet": "market forecast", "publishedDate": "2026-01-01"},
        {"url": "https://example.org/news", "title": "industry news", "snippet": "players", "source_type": "news"},
        {"url": "https://arxiv.org/abs/1", "title": "research paper", "snippet": "battery technology"},
    ]
    summary = summarize_screening_candidates(candidates, infer_research_intent("航空機電動化の市場動向", "market", "deep"))
    assert summary["top_domains"]
    assert summary["source_type_counts"]
    assert summary["freshness_counts"]
    assert summary["domain_count"] == 3


def test_focused_plan_contains_topic_anchored_queries():
    intent = infer_research_intent("航空機電動化の市場動向", "market", "deep")
    plan = build_focused_research_plan(intent, {"off_topic_patterns": ["game"]}, depth="deep")
    queries = [q["query"] for q in plan["focused_queries"]]
    assert queries
    assert all("航空機電動化" in q for q in queries)
    assert all(q.lower() != "web analysis" for q in queries)
    assert "game" in plan["exclusion_terms"]


def test_focused_plan_covers_required_dimensions():
    intent = infer_research_intent("航空機電動化の市場動向", "market", "deep")
    plan = build_focused_research_plan(intent, {}, depth="deep")
    for dim in ["market_size", "key_players", "regulation", "risks"]:
        assert dim in plan["must_cover_dimensions"]


def test_source_mix_targets_created():
    intent = infer_research_intent("航空機電動化の市場動向", "market", "deep")
    plan = build_focused_research_plan(intent, {}, depth="deep")
    for key in ["official", "report_pdf", "news_recent", "company_ir"]:
        assert plan["source_mix_targets"][key] > 0


def test_coverage_matrix_marks_missing_dimensions():
    plan = {"must_cover_dimensions": ["market_size", "regulation"]}
    matrix = build_coverage_matrix(plan, [{"citation_label": "[S1]", "quote": "market size forecast CAGR"}], [])
    by_dim = {row["dimension"]: row for row in matrix}
    assert by_dim["market_size"]["status"] == "weak"
    assert by_dim["regulation"]["status"] == "missing"


def test_report_outline_uses_intent():
    intent = infer_research_intent("航空機電動化の市場動向", "market", "deep")
    outline = build_report_outline(intent, {})
    assert "市場概況" in outline
    assert "主要プレイヤー" in outline


def test_retrieval_summary_contains_screening_and_plan(monkeypatch):
    monkeypatch.setenv("DEEP_RESEARCH_LLM_ENABLED", "0")
    intent = infer_research_intent("航空機電動化の市場動向", "market", "deep")
    plan = build_focused_research_plan(intent, {}, depth="deep")
    retrieval_summary = {
        "intent": intent,
        "screening_summary": {"candidate_count": 200},
        "focused_research_plan": plan,
        "source_mix": {"official": 1},
        "coverage_matrix": [{"dimension": "market_size", "status": "missing"}],
    }
    payload = build_answer_payload(question="q", references=[], retrieval_summary=retrieval_summary)
    assert payload["retrieval_summary"]["intent"]
    assert payload["retrieval_summary"]["screening_summary"]
    assert payload["retrieval_summary"]["focused_research_plan"]
    assert payload["retrieval_summary"]["source_mix"]
    assert payload["retrieval_summary"]["coverage_matrix"]
