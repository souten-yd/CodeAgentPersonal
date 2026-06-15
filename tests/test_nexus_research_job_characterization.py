"""Characterization tests for run_research_job.

These pin the externally-observable behavior of the orchestrator (the returned dict shape and
the ordered sequence of emitted job-event types) with the real control flow intact and only the
I/O boundaries mocked (web search, downloads, source/evidence persistence, citation map, answer
LLM, gap analysis). They exist to guard the staged phase extraction of the 970-line
run_research_job: any extraction that preserves behavior keeps these green; any that changes the
emitted phase/event order or result shape fails loudly.

The captured sequences are golden values recorded from the pre-refactor implementation.
"""

from __future__ import annotations

import uuid
from contextlib import ExitStack
from unittest.mock import patch

from app.nexus.jobs import create_job
from app.nexus.research_agent import ResearchAgentInput, run_research_job


def _io_boundary_patches(
    *,
    search_items: list[dict],
    candidates: list[dict],
    downloaded: list[dict],
    registered: list[dict] | list[list[dict]],
    gap_analyses: list[dict] | dict,
    captured_events: list[tuple[str, dict]],
):
    """Patch only the true I/O boundaries; let the orchestration logic run for real."""
    register_kw = (
        {"side_effect": registered}
        if registered and isinstance(registered[0], list)
        else {"return_value": registered}
    )
    gap_kw = {"side_effect": gap_analyses} if isinstance(gap_analyses, list) else {"return_value": gap_analyses}
    patches = [
        patch("app.nexus.research_agent.plan_web_queries", return_value=["q"]),
        patch("app.nexus.research_agent.run_web_search", return_value={"items": list(search_items)}),
        patch("app.nexus.research_agent.collect_source_candidates", return_value=list(candidates)),
        patch("app.nexus.research_agent.rank_source_candidates", side_effect=lambda cands, **_kw: list(cands)),
        patch("app.nexus.research_agent._download_sources_parallel", return_value=(list(downloaded), 0)),
        patch("app.nexus.research_agent.register_or_update_sources", **register_kw),
        patch("app.nexus.research_agent._build_evidence_from_sources", return_value=[]),
        patch("app.nexus.research_agent.save_evidence_items", return_value=0),
        patch("app.nexus.research_agent.replace_evidence_items_for_job", return_value=0),
        patch("app.nexus.research_agent._load_source_chunks", return_value=[]),
        patch("app.nexus.research_agent.build_citation_map", return_value=[]),
        patch(
            "app.nexus.research_agent.build_answer_payload",
            return_value={"answer": "ok", "answer_markdown": "ok", "references": [], "evidence": []},
        ),
        patch("app.nexus.research_agent._analyze_research_gaps", **gap_kw),
        patch("app.nexus.research_agent._persist_latest_answer_json", return_value=None),
        patch(
            "app.nexus.research_agent.append_job_event",
            side_effect=lambda _jid, et, payload: captured_events.append((et, payload)),
        ),
        patch("app.nexus.research_agent.append_job_heartbeat", return_value=None),
        patch("app.nexus.research_agent.update_job", return_value=None),
    ]
    return patches


def _run(payload: ResearchAgentInput, *, job_id: str, **kw) -> tuple[dict, list[str]]:
    captured: list[tuple[str, dict]] = []
    with ExitStack() as stack:
        for p in _io_boundary_patches(captured_events=captured, **kw):
            stack.enter_context(p)
        result = run_research_job(payload, job_id=job_id)
    event_types = [et for et, _ in captured]
    return result, event_types


class RunResearchJobCharacterizationTests:
    pass


def test_characterize_non_recursive_standard_run():
    job_id = f"char-std-{uuid.uuid4().hex[:8]}"
    create_job(job_id, title="char", status="queued", message="queued")
    result, event_types = _run(
        ResearchAgentInput(query="characterization standard", max_sources=2),
        job_id=job_id,
        search_items=[{"url": "https://example.com/1", "title": "S1", "snippet": "x"}],
        candidates=[{"url": "https://example.com/1", "title": "S1"}],
        downloaded=[{"source_id": "src-1", "url": "https://example.com/1", "final_url": "https://example.com/1", "status": "downloaded", "size": 10}],
        registered=[{"source_id": "src-1", "url": "https://example.com/1", "final_url": "https://example.com/1", "status": "downloaded"}],
        gap_analyses={"confidence": 0.5, "unresolved_items": [], "claim_analysis": {}},
    )

    assert set(result.keys()) == {"job_id", "queries", "search", "sources", "answer"}
    assert result["job_id"] == job_id
    assert result["answer"]["recursive_search"] is False
    assert result["answer"]["answer_saved"] is True
    # Golden phase/event ordering for a clean non-recursive run.
    assert event_types == GOLDEN_NON_RECURSIVE


def test_characterize_recursive_two_iteration_run():
    job_id = f"char-rec-{uuid.uuid4().hex[:8]}"
    create_job(job_id, title="char", status="queued", message="queued")
    result, event_types = _run(
        ResearchAgentInput(query="characterization recursive", recursive_search=True, max_iterations=2, max_sources=2),
        job_id=job_id,
        search_items=[{"url": "https://example.com/new", "title": "new"}],
        candidates=[{"url": "https://example.com/new", "title": "new"}],
        downloaded=[{"source_id": "src-2", "url": "https://example.com/new", "final_url": "https://example.com/new", "status": "downloaded", "size": 10}],
        registered=[
            [{"source_id": "src-1", "url": "https://example.com/old", "final_url": "https://example.com/old", "status": "downloaded"}],
            [{"source_id": "src-2", "url": "https://example.com/new", "final_url": "https://example.com/new", "status": "downloaded"}],
        ],
        gap_analyses=[
            {"confidence": 0.1, "gaps": ["source_count_low"], "unresolved_items": [], "claim_analysis": {"claim_count": 1, "gaps": []}},
            {"confidence": 0.9, "gaps": [], "unresolved_items": [], "claim_analysis": {"claim_count": 0, "gaps": []}},
        ],
    )

    assert result["answer"]["recursive_search"] is True
    assert "recursive_iteration_started" in event_types
    assert "claim_support_verified" in event_types
    assert event_types == GOLDEN_RECURSIVE


# Golden sequences recorded from the pre-refactor implementation.
GOLDEN_NON_RECURSIVE: list[str] = [
    "planning_started", "state_transition", "planning_finished", "web_search_started",
    "state_transition", "retrieval_round_started", "download_phase_started",
    "retrieval_round_completed", "retrieval_round_started", "retrieval_round_completed",
    "replenishment_round_started", "replenishment_search_started", "web_search_finished",
    "source_collection_started", "state_transition", "source_collection_finished",
    "download_phase_finished", "source_ingest_started", "source_ingest_finished",
    "evidence_retrieval_started", "state_transition", "evidence_retrieval_finished",
    "evidence_compression_started", "evidence_compression_finished", "state_transition",
    "answer_llm_request_started", "answer_llm_request_failed", "answer_validation_started",
    "answer_validation_finished", "answer_save_started", "answer_save_finished",
    "state_transition", "research_completed", "research_degraded",
]
GOLDEN_RECURSIVE: list[str] = [
    "planning_started", "state_transition", "planning_finished", "web_search_started",
    "state_transition", "retrieval_round_started", "download_phase_started",
    "retrieval_round_completed", "retrieval_round_started", "retrieval_round_completed",
    "replenishment_round_started", "replenishment_search_started", "web_search_finished",
    "source_collection_started", "state_transition", "source_collection_finished",
    "download_phase_finished", "source_ingest_started", "source_ingest_finished",
    "evidence_retrieval_started", "state_transition", "evidence_retrieval_finished",
    "evidence_compression_started", "evidence_compression_finished", "state_transition",
    "answer_llm_request_started", "recursive_iteration_started", "recursive_gap_analysis_started",
    "recursive_gap_analysis_finished", "claim_support_verified",
    "recursive_followup_queries_generated", "recursive_followup_search_started",
    "recursive_stopped", "recursive_iteration_finished", "answer_llm_request_failed",
    "answer_validation_started", "answer_validation_finished", "answer_save_started",
    "answer_save_finished", "state_transition", "research_completed", "research_degraded",
]
