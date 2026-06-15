"""Orchestration tests for the extracted _run_recursive_phase.

After run_research_job was split, the recursive follow-up loop is a standalone function with an
explicit interface, so the stop-reason behavior that the old brittle full-flow mocks tried to
assert can be exercised directly and robustly here (these replace the skipped recursive tests in
test_nexus_research_agent.py).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from app.nexus.research_agent import ResearchAgentInput, _run_recursive_phase


_RUNTIME_CFG = SimpleNamespace(
    download_concurrency=2,
    pdf_extract_concurrency=1,
    download_progress_interval_sec=1,
    download_stalled_after_sec=30,
)


def _call(payload: ResearchAgentInput, *, gap_analyses, **overrides):
    captured: list[tuple[str, dict]] = []
    kwargs = dict(
        effective_job_id="job-rec",
        query="q",
        summary="summary",
        registered_sources=[{"source_id": "src-1", "url": "https://example.com/old", "final_url": "https://example.com/old", "status": "downloaded"}],
        source_chunks=[],
        references=[],
        answer_payload={"answer": "ok"},
        retrieval_summary={},
        downloadable_sources=[{"source_id": "src-1", "status": "downloaded", "size": 10}],
        recursive_reserved_downloads=10,
        max_total_download_bytes=100_000,
        max_download_bytes=10_000,
        download_timeout_sec=5,
        runtime_cfg=_RUNTIME_CFG,
    )
    kwargs.update(overrides)
    gap_kw = {"side_effect": gap_analyses} if isinstance(gap_analyses, list) else {"return_value": gap_analyses}
    with patch("app.nexus.research_agent._analyze_research_gaps", **gap_kw), patch(
        "app.nexus.research_agent.append_job_event", side_effect=lambda _j, et, p: captured.append((et, p))
    ), patch("app.nexus.research_agent.run_web_search", return_value={"items": [{"url": "https://example.com/new"}]}), patch(
        "app.nexus.research_agent.collect_source_candidates", return_value=[{"url": "https://example.com/new"}]
    ), patch("app.nexus.research_agent.rank_source_candidates", side_effect=lambda c, **_k: list(c)), patch(
        "app.nexus.research_agent._download_sources_parallel",
        return_value=([{"source_id": "src-2", "url": "https://example.com/new", "final_url": "https://example.com/new", "status": "downloaded", "size": 10}], 0),
    ), patch(
        "app.nexus.research_agent.register_or_update_sources",
        return_value=[{"source_id": "src-2", "url": "https://example.com/new", "final_url": "https://example.com/new", "status": "downloaded"}],
    ), patch("app.nexus.research_agent._load_source_chunks", return_value=[]), patch(
        "app.nexus.research_agent.build_citation_map", return_value=[]
    ), patch(
        "app.nexus.research_agent.normalize_reference_labels",
        side_effect=lambda references, evidence_json, evidence_chunks: {"references": references, "evidence_json": evidence_json, "evidence_chunks": evidence_chunks},
    ), patch("app.nexus.research_agent.build_answer_payload", return_value={"answer": "ok"}), patch(
        "app.nexus.research_agent._build_evidence_from_sources", return_value=[]
    ), patch("app.nexus.research_agent.replace_evidence_items_for_job", return_value=0):
        result = _run_recursive_phase(payload, **kwargs)
    return result, [et for et, _ in captured]


def test_non_recursive_runs_single_gap_analysis():
    payload = ResearchAgentInput(query="q", recursive_search=False)
    result, events = _call(payload, gap_analyses={"confidence": 0.4, "unresolved_items": ["x"]})
    assert result["iterations"] == []
    assert result["final_confidence"] == 0.4
    assert result["unresolved_items"] == ["x"]
    assert "recursive_iteration_started" not in events


def test_confidence_threshold_reached_stops_before_followup():
    payload = ResearchAgentInput(query="q", recursive_search=True, max_iterations=1, confidence_threshold=0.75)
    result, events = _call(payload, gap_analyses={"confidence": 0.9, "unresolved_items": []})
    assert result["recursive_stop_reason"] == "confidence_threshold_reached"
    assert result["followup_search_count"] == 0
    assert "recursive_followup_search_started" not in events


def test_no_followup_queries_stops_iteration():
    payload = ResearchAgentInput(query="q", recursive_search=True, max_iterations=1, confidence_threshold=0.95)
    with patch("app.nexus.research_agent._generate_followup_queries", return_value=[]):
        result, events = _call(payload, gap_analyses={"confidence": 0.1, "gaps": [], "unresolved_items": []})
    assert result["recursive_stop_reason"] == "no_followup_queries"
    assert result["followup_search_count"] == 0


def test_download_budget_exhausted_stops():
    payload = ResearchAgentInput(query="q", recursive_search=True, max_iterations=2, confidence_threshold=0.95)
    with patch("app.nexus.research_agent._generate_followup_queries", return_value=["fq"]):
        result, events = _call(
            payload,
            gap_analyses={"confidence": 0.1, "gaps": ["source_count_low"], "unresolved_items": ["x"]},
            max_total_download_bytes=0,
        )
    assert result["recursive_stop_reason"] == "download_budget_exhausted"
    assert "recursive_stopped" in events


def test_followup_then_max_iterations_reached():
    payload = ResearchAgentInput(query="q", recursive_search=True, max_iterations=1, confidence_threshold=0.95)
    with patch("app.nexus.research_agent._generate_followup_queries", return_value=["fq"]):
        result, events = _call(payload, gap_analyses={"confidence": 0.2, "gaps": ["g"], "unresolved_items": []})
    assert result["recursive_stop_reason"] == "max_iterations_reached"
    assert result["followup_search_count"] == 1
    assert result["added_sources_total"] == 1
    assert "recursive_followup_search_finished" in events
