from types import SimpleNamespace

from app.nexus.research_api import ResearchRunRequest
from app.services.nexus_execution import (
    run_nexus_deep_research_service,
    run_nexus_recursive_research_service,
    run_nexus_research_service,
)


def test_deep_research_service_applies_deep_defaults():
    captured = {}

    def fake_run(payload):
        captured["payload"] = payload
        return {"job_id": "job-deep"}

    result = run_nexus_deep_research_service(SimpleNamespace(query="q"), run_research_async=fake_run)

    assert result["job_id"] == "job-deep"
    payload = captured["payload"]
    assert isinstance(payload, ResearchRunRequest)
    assert payload.mode == "deep"
    assert payload.depth == "deep"
    assert payload.max_queries == 6
    assert payload.max_results_per_query == 8
    assert payload.max_sources == 100
    assert payload.max_downloads == 48
    assert payload.prefer_pdf is True
    assert payload.official_first is True
    assert payload.continue_on_download_error is True
    assert payload.source_profile == "web"
    assert payload.confidence_threshold == 0.78
    assert payload.stop_when_sufficient is True
    assert payload.recursive_search is False


def test_deep_research_service_preserves_user_limits():
    captured = {}

    def fake_run(payload):
        captured["payload"] = payload
        return {"job_id": "job-deep"}

    run_nexus_deep_research_service(
        SimpleNamespace(query="q", max_queries=3, max_sources=9, recursive_search=True),
        run_research_async=fake_run,
    )

    payload = captured["payload"]
    assert payload.max_queries == 3
    assert payload.max_sources == 9
    assert payload.recursive_search is True


def test_recursive_research_service_enables_recursive_defaults():
    captured = {}

    def fake_run(payload):
        captured["payload"] = payload
        return {"job_id": "job-rec"}

    run_nexus_recursive_research_service(SimpleNamespace(query="q"), run_research_async=fake_run)

    payload = captured["payload"]
    assert payload.mode == "deep"
    assert payload.depth == "deep"
    assert payload.recursive_search is True
    assert payload.max_iterations >= 2
    assert payload.max_followup_queries == 4


def test_standard_research_service_passes_payload_through():
    payload = ResearchRunRequest(query="q")
    captured = {}

    def fake_run(p):
        captured["payload"] = p
        return {"job_id": "job-standard"}

    run_nexus_research_service(payload, run_research_async=fake_run)

    assert captured["payload"] is payload
