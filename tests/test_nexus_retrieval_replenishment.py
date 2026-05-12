from app.nexus.research_agent import (
    _init_replenishment_metrics,
    _retrieval_summary,
    _select_replenishment_candidates,
    compute_retrieval_deficit,
)
from app.nexus.research_planner import build_replenishment_queries
from app.nexus.web_scout import choose_replacement_engines


def test_compute_deficit_from_failed_candidates():
    deficit = compute_retrieval_deficit(
        {
            "valid_source_count": 20,
            "evidence_count": 60,
            "failed_sources": [{"status": "failed"} for _ in range(10)],
            "source_mix": {},
            "source_mix_targets": {},
        },
        {"target_valid_source_count": 35, "target_evidence_count": 100, "target_replacement_ratio": 1.0, "max_replenishment_candidates": 80},
    )
    assert deficit["valid_source_deficit"] == 15
    assert deficit["failed_candidate_count"] == 10
    assert deficit["replacement_needed"] is True
    assert deficit["replacement_target_count"] == 15


def test_skipped_limit_not_counted_as_quality_failure():
    deficit = compute_retrieval_deficit(
        {
            "valid_source_count": 10,
            "evidence_count": 50,
            "failed_sources": [{"status": "skipped_download_limit"}],
            "source_mix": {},
            "source_mix_targets": {},
        },
        {"target_valid_source_count": 18, "target_evidence_count": 50, "target_replacement_ratio": 1.0, "max_replenishment_candidates": 20},
    )
    assert deficit["failed_candidate_count"] == 1
    assert deficit["replacement_needed"] is True
    assert deficit["replacement_target_count"] == 8


def test_failed_google_query_retried_with_brave_or_duckduckgo():
    engines = choose_replacement_engines("market", "google", {"google"})
    assert "google" not in engines
    assert {"brave", "duckduckgo"}.issubset(set(engines))


def test_all_broad_engines_suspended_falls_back_to_safe():
    engines = choose_replacement_engines("source", None, {"google", "brave", "duckduckgo"})
    assert "wikipedia" in engines
    assert "wikidata" in engines
    assert "arxiv" in engines
    assert "google" not in engines


def test_replenishment_loop_downloads_next_best_unattempted_candidates():
    ranked = [
        {"url": "https://already.example/report.pdf", "title": "already PDF", "is_pdf": True},
        {"url": "https://agency.gov/report.pdf", "title": "official report PDF", "is_pdf": True, "is_official": True},
    ]
    selected = _select_replenishment_candidates(
        ranked,
        {"https://already.example/report.pdf"},
        1,
        {"pdf_deficit": 1, "official_deficit": 1},
    )
    assert selected == [ranked[1]]


def test_replenishment_stops_when_targets_satisfied():
    deficit = compute_retrieval_deficit(
        {"valid_source_count": 35, "evidence_count": 100, "failed_sources": [], "source_mix": {}, "source_mix_targets": {}},
        {"target_valid_source_count": 35, "target_evidence_count": 100, "max_replenishment_candidates": 80},
    )
    assert deficit["replacement_needed"] is False
    assert deficit["replacement_target_count"] == 0


def test_source_mix_deficit_prioritizes_pdf_or_official():
    ranked = [
        {"url": "https://blog.example/post", "title": "analysis"},
        {"url": "https://nasa.gov/electric-aircraft/report.pdf", "title": "official PDF report", "is_pdf": True, "is_official": True},
    ]
    selected = _select_replenishment_candidates(ranked, set(), 1, {"pdf_deficit": 1, "official_deficit": 1})
    assert selected[0]["url"].endswith("report.pdf")


def test_replacement_queries_keep_topic_anchor():
    queries = build_replenishment_queries(
        "航空機電動化の市場動向",
        {"source_profile": "market"},
        {"source_mix_targets": {"official": 1}},
        {"official_deficit": 1, "pdf_deficit": 1},
        [{"url": "https://offtopic.example/x", "failure_class": "off_topic"}],
        ["google"],
    )
    assert queries
    assert all("航空機電動化の市場動向" in item["query"] for item in queries)
    assert all("google" in item["avoid_engines"] for item in queries)


def test_retrieval_summary_contains_replenishment_metrics():
    metrics = _init_replenishment_metrics(True)
    metrics.update({"attempted": True, "replacement_queries": 2, "replacement_candidates": 8, "replacement_downloads": 3, "replacement_valid_sources": 2})
    summary = _retrieval_summary(
        targets={"replenishment_enabled": True},
        retrieval_rounds=[],
        candidate_count=0,
        attempted_download_count=0,
        registered_sources=[],
        evidence_chunks=[],
        skipped_due_to_download_limit_count=0,
        engine_replenishment=metrics,
    )
    assert summary["engine_replenishment"]["enabled"] is True
    assert summary["engine_replenishment"]["attempted"] is True
    assert summary["engine_replenishment"]["replacement_valid_sources"] == 2
