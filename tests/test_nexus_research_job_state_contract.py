from app.nexus import research_agent
from app.nexus.research_agent import ResearchAgentInput, _determine_final_research_outcome


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


def test_run_research_job_zero_sources_updates_failed_not_completed(monkeypatch):
    updates, events = [], []

    monkeypatch.setattr(research_agent, "load_runtime_config", lambda: type("C", (), {
        "max_downloads": 1, "max_download_mb": 1, "max_total_download_mb": 1, "download_timeout_sec": 1,
        "download_concurrency": 1, "pdf_extract_concurrency": 1, "download_progress_interval_sec": 1, "download_stalled_after_sec": 1,
    })())
    monkeypatch.setattr(research_agent, "create_job", lambda *a, **k: None)
    monkeypatch.setattr(research_agent, "ensure_job_exists", lambda *a, **k: None)
    monkeypatch.setattr(research_agent, "update_job", lambda *a, **k: updates.append(k))
    monkeypatch.setattr(research_agent, "append_job_event", lambda _j, t, p: events.append((t, p)))
    monkeypatch.setattr(research_agent, "_emit_phase", lambda *a, **k: None)
    monkeypatch.setattr(research_agent, "_record_state", lambda *a, **k: None)
    monkeypatch.setattr(research_agent, "infer_research_intent", lambda *a, **k: {})
    monkeypatch.setattr(research_agent, "get_screening_settings", lambda *a, **k: {"enabled": False})
    monkeypatch.setattr(research_agent, "build_focused_research_plan", lambda *a, **k: {"focused_queries": []})
    monkeypatch.setattr(research_agent, "build_report_outline", lambda *a, **k: {})
    monkeypatch.setattr(research_agent, "plan_web_queries", lambda *a, **k: ["q"])
    monkeypatch.setattr(research_agent, "run_web_search", lambda *a, **k: {"items": []})
    monkeypatch.setattr(research_agent, "collect_source_candidates", lambda *a, **k: [])
    monkeypatch.setattr(research_agent, "rank_source_candidates", lambda *a, **k: [])
    monkeypatch.setattr(research_agent, "_filter_stub_candidates", lambda ranked, _payload: (ranked, 1))
    monkeypatch.setattr(research_agent, "analyze_claim_level_gaps", lambda *a, **k: {})
    monkeypatch.setattr(research_agent, "save_minimal_research_answer", lambda *a, **k: None)

    research_agent.run_research_job(ResearchAgentInput(query="q"), job_id="job-test-0")

    assert updates[-1]["status"] == "failed"
    completed = [p for t, p in events if t == "research_completed"][-1]
    assert completed["status"] == "failed"
    assert completed["reason"] == "no_sources"
    assert completed["phase"] == "no_sources"
    assert completed["source_count"] == 0
    assert completed["evidence_count"] == 0


def test_run_research_job_sources_without_evidence_degraded(monkeypatch):
    updates, events = [], []
    monkeypatch.setattr(research_agent, "load_runtime_config", lambda: type("C", (), {
        "max_downloads": 1, "max_download_mb": 1, "max_total_download_mb": 1, "download_timeout_sec": 1,
        "download_concurrency": 1, "pdf_extract_concurrency": 1, "download_progress_interval_sec": 1, "download_stalled_after_sec": 1,
    })())
    monkeypatch.setattr(research_agent, "create_job", lambda *a, **k: None)
    monkeypatch.setattr(research_agent, "ensure_job_exists", lambda *a, **k: None)
    monkeypatch.setattr(research_agent, "update_job", lambda *a, **k: updates.append(k))
    monkeypatch.setattr(research_agent, "append_job_event", lambda _j, t, p: events.append((t, p)))
    monkeypatch.setattr(research_agent, "_emit_phase", lambda *a, **k: None)
    monkeypatch.setattr(research_agent, "_record_state", lambda *a, **k: None)
    monkeypatch.setattr(research_agent, "infer_research_intent", lambda *a, **k: {})
    monkeypatch.setattr(research_agent, "get_screening_settings", lambda *a, **k: {"enabled": False})
    monkeypatch.setattr(research_agent, "build_focused_research_plan", lambda *a, **k: {"focused_queries": []})
    monkeypatch.setattr(research_agent, "build_report_outline", lambda *a, **k: {})
    monkeypatch.setattr(research_agent, "plan_web_queries", lambda *a, **k: ["q"])
    monkeypatch.setattr(research_agent, "run_web_search", lambda *a, **k: {"items": [{"url": "https://example.com"}]})
    monkeypatch.setattr(research_agent, "collect_source_candidates", lambda *a, **k: [{"url": "https://example.com"}])
    monkeypatch.setattr(research_agent, "rank_source_candidates", lambda items, **k: items)
    monkeypatch.setattr(research_agent, "_filter_stub_candidates", lambda ranked, _payload: (ranked, 0))
    monkeypatch.setattr(research_agent, "_select_download_candidates", lambda c, *a, **k: c)
    monkeypatch.setattr(research_agent, "_download_sources_parallel", lambda **k: ([{"source_id": "s1", "url": "https://example.com", "status": "downloaded"}], 0))
    monkeypatch.setattr(research_agent, "register_or_update_sources", lambda **k: [{"source_id": "s1", "status": "downloaded"}])
    monkeypatch.setattr(research_agent, "_load_source_chunks", lambda *a, **k: [])
    monkeypatch.setattr(research_agent, "_retrieval_summary", lambda **k: {"valid_source_count": 1, "evidence_count": 0, "targets_satisfied": True})
    monkeypatch.setattr(research_agent, "replace_evidence_items_for_job", lambda *a, **k: None)
    monkeypatch.setattr(research_agent, "save_evidence_items", lambda *a, **k: 0)
    monkeypatch.setattr(research_agent, "build_answer_payload", lambda **k: {"generation": {"mode": "llm_answer"}, "retrieval_summary": {"valid_source_count": 1, "evidence_count": 0, "targets_satisfied": True}})
    monkeypatch.setattr(research_agent, "analyze_claim_level_gaps", lambda *a, **k: {})

    research_agent.run_research_job(ResearchAgentInput(query="q"), job_id="job-test-1")

    assert updates[-1]["status"] == "degraded"
    completed = [p for t, p in events if t == "research_completed"][-1]
    assert completed["status"] == "degraded"
    assert completed["reason"] == "no_evidence"
    assert completed["status"] != "completed"
