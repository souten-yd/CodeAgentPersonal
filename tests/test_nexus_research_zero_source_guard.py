from app.nexus.research_agent import _determine_final_research_outcome


def test_zero_sources_never_completed():
    out = _determine_final_research_outcome(
        retrieval_summary={"valid_source_count": 0, "evidence_count": 0},
        registered_sources=[],
        evidence_chunks=[],
        answer_payload={"generation": {"mode": "template_fallback"}},
        download_error_count=0,
        source_has_degraded_or_failed=False,
    )
    assert out["status"] in {"failed", "degraded"}
    assert out["status"] != "completed"
    assert "no_sources" in out["reason"]


def test_template_fallback_with_zero_sources_is_failed():
    out = _determine_final_research_outcome(
        retrieval_summary={"valid_source_count": 0, "evidence_count": 1},
        registered_sources=[],
        evidence_chunks=[{"chunk_id": "x"}],
        answer_payload={"generation_mode": "template_fallback"},
        download_error_count=0,
        source_has_degraded_or_failed=False,
    )
    assert out["status"] in {"failed", "degraded"}
    assert out["status"] != "completed"


def test_zero_evidence_with_sources_is_degraded():
    out = _determine_final_research_outcome(
        retrieval_summary={"valid_source_count": 2, "evidence_count": 0},
        registered_sources=[{"source_id": "s1"}],
        evidence_chunks=[],
        answer_payload={"generation": {"mode": "llm_answer"}},
        download_error_count=0,
        source_has_degraded_or_failed=False,
    )
    assert out["status"] == "degraded"
    assert out["status"] != "completed"


def test_targets_unsatisfied_but_some_sources_is_degraded():
    out = _determine_final_research_outcome(
        retrieval_summary={"valid_source_count": 2, "evidence_count": 3, "targets_satisfied": False},
        registered_sources=[{"source_id": "s1"}],
        evidence_chunks=[{"chunk_id": "c1"}],
        answer_payload={"generation": {"mode": "llm_answer"}},
        download_error_count=0,
        source_has_degraded_or_failed=False,
    )
    assert out["status"] == "degraded"


def test_should_expand_retrieval_is_not_enough():
    out = _determine_final_research_outcome(
        retrieval_summary={"valid_source_count": 1, "evidence_count": 1, "targets_satisfied": False},
        registered_sources=[{"source_id": "s1"}],
        evidence_chunks=[{"chunk_id": "c1"}],
        answer_payload={"generation": {"mode": "llm_answer"}},
        download_error_count=0,
        source_has_degraded_or_failed=False,
    )
    assert out["status"] == "degraded"
