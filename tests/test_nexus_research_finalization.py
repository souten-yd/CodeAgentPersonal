from app.nexus.research_agent import _determine_final_research_outcome


def test_answer_generated_with_citation_issues_becomes_degraded():
    out = _determine_final_research_outcome(
        retrieval_summary={"valid_source_count": 2, "evidence_count": 2, "targets_satisfied": True},
        registered_sources=[{"source_id": "s1"}],
        evidence_chunks=[{"chunk_id": "c1"}],
        answer_payload={"answer_generated": True, "citation_verification": {"warnings": [{"reason": "low_overlap"}]}, "unresolved_items": []},
        download_error_count=0,
        source_has_degraded_or_failed=False,
    )
    assert out["status"] == "degraded"


def test_answer_generated_with_unresolved_items_becomes_degraded():
    out = _determine_final_research_outcome(
        retrieval_summary={"valid_source_count": 2, "evidence_count": 2, "targets_satisfied": True},
        registered_sources=[{"source_id": "s1"}],
        evidence_chunks=[{"chunk_id": "c1"}],
        answer_payload={"answer_generated": True, "citation_verification": {"warnings": []}, "unresolved_items": [{"claim": "x"}]},
        download_error_count=0,
        source_has_degraded_or_failed=False,
    )
    assert out["status"] == "degraded"


def test_answer_not_generated_is_not_force_completed():
    out = _determine_final_research_outcome(
        retrieval_summary={"valid_source_count": 0, "evidence_count": 0},
        registered_sources=[],
        evidence_chunks=[],
        answer_payload={"answer_generated": False, "generation_mode": "template_fallback"},
        download_error_count=0,
        source_has_degraded_or_failed=False,
    )
    assert out["status"] in {"failed", "degraded"}
