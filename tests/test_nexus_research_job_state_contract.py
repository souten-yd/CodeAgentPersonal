from app.nexus.research_agent import _determine_final_research_outcome


def test_no_sources_contract_failed_state():
    out = _determine_final_research_outcome(
        retrieval_summary={"valid_source_count": 0, "evidence_count": 0},
        registered_sources=[], evidence_chunks=[], answer_payload={}, download_error_count=0, source_has_degraded_or_failed=False
    )
    assert out["status"] == "failed"
    assert out["phase"] == "no_sources"


def test_no_evidence_contract_degraded_state():
    out = _determine_final_research_outcome(
        retrieval_summary={"valid_source_count": 3, "evidence_count": 0},
        registered_sources=[{"id": 1}], evidence_chunks=[], answer_payload={}, download_error_count=0, source_has_degraded_or_failed=False
    )
    assert out["status"] == "degraded"
    assert out["phase"] == "no_evidence"
