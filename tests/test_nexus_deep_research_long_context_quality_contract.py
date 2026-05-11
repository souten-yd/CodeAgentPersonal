from types import SimpleNamespace

from app.nexus.answer_builder import build_answer_payload
from app.services import nexus_execution
from app.services.nexus_execution import run_nexus_deep_research_service


def test_long_context_env_expands_deep_defaults(monkeypatch):
    monkeypatch.setenv("NEXUS_DEEP_RESEARCH_CONTEXT_PROFILE", "long_64k")
    captured = {}

    def fake_run(payload):
        captured["payload"] = payload
        return {"job_id": "job-long"}

    result = run_nexus_deep_research_service(SimpleNamespace(query="q"), run_research_async=fake_run)
    payload = captured["payload"]
    assert result["job_id"] == "job-long"
    assert payload.max_sources >= 60
    assert payload.max_downloads >= 24
    assert payload.max_queries >= 8
    assert payload.max_results_per_query >= 10
    assert payload.max_followup_queries >= 6
    assert payload.confidence_threshold >= 0.82
    assert payload.prefer_pdf is True
    assert payload.official_first is True


def test_long_context_defaults_preserve_user_limits(monkeypatch):
    monkeypatch.setenv("NEXUS_ANSWER_LLM_MAX_CONTEXT_TOKENS", "65535")
    captured = {}

    def fake_run(payload):
        captured["payload"] = payload
        return {"job_id": "job-user"}

    run_nexus_deep_research_service(
        SimpleNamespace(query="q", max_sources=7, max_downloads=5, max_queries=2),
        run_research_async=fake_run,
    )
    payload = captured["payload"]
    assert payload.max_sources == 7
    assert payload.max_downloads == 5
    assert payload.max_queries == 2
    assert payload.max_results_per_query == 10


def test_answer_payload_exposes_64k_context_budget(monkeypatch):
    monkeypatch.setenv("NEXUS_ANSWER_LLM_MAX_CONTEXT_TOKENS", "65535")
    monkeypatch.setenv("LLAMA_CTX_SIZE", "65535")
    monkeypatch.setenv("DEEP_RESEARCH_LLM_ENABLED", "0")
    monkeypatch.setattr(nexus_execution, "_is_long_context_deep_research", lambda: True)
    monkeypatch.setattr("app.nexus.answer_builder._resolve_answer_llm_settings", lambda: {
        "endpoint": "",
        "model": "local-llm",
        "enabled": False,
        "reachable": False,
        "model_role": "SEARCH",
        "model_source": "fallback",
        "probe_error": "",
        "selected_reason": "test",
        "probe_status": [],
        "search_assignment": {},
    })
    payload = build_answer_payload(
        question="alpha beta",
        references=[{"source_id": "s1", "source_type": "official", "title": "Official", "url": "https://example.com/report.pdf", "is_official": True}],
        evidence_chunks=[{"source_id": "s1", "chunk_id": "c1", "citation_label": "[S1]", "quote": "alpha beta " * 100, "content_type": "application/pdf"}],
    )
    assert payload["model_context_tokens"] == 65535
    assert payload["context_profile"] == "long_64k"
    assert payload["context_budget"]["max_context_tokens"] == 65535
    assert payload["context_budget"]["max_evidence_chunks"] >= 96
    assert payload["compression_stats"]["compression_profile"] == "long_64k"
    assert payload["estimated_prompt_tokens"] > 0
