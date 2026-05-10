from types import SimpleNamespace

import pytest

from app.services.nexus_execution import NexusExecutionError, run_nexus_research_followup_service


class RequestFactory:
    def __call__(self, **kwargs):
        return SimpleNamespace(**kwargs)


def test_existing_sources_followup_searches_chunks_without_research():
    calls = {"search": 0, "research": 0}

    def search_chunks(request):
        calls["search"] += 1
        assert request.job_id == "parent"
        return [{"citation_label": "[S1]", "title": "T", "snippet": "hit"}]

    def run_research(_payload):
        calls["research"] += 1
        return {}

    result = run_nexus_research_followup_service(
        "parent",
        SimpleNamespace(question="q", use_existing_sources_only=True, limit=5),
        search_chunks=search_chunks,
        source_search_request_factory=RequestFactory(),
        run_research_async=run_research,
    )

    assert calls == {"search": 1, "research": 0}
    assert result["mode"] == "existing_sources"
    assert result["parent_job_id"] == "parent"
    assert result["use_existing_sources_only"] is True


def test_deep_search_followup_starts_new_research_job():
    captured = {}

    def run_research(payload):
        captured["payload"] = payload
        return {"job_id": "child", "job": {"job_id": "child"}, "queries": ["q"]}

    result = run_nexus_research_followup_service(
        "parent",
        SimpleNamespace(question="q", use_existing_sources_only=False, max_iterations=2, max_queries=4),
        search_chunks=lambda _request: [],
        source_search_request_factory=RequestFactory(),
        run_research_async=run_research,
    )

    assert result["job_id"] == "child"
    assert result["parent_job_id"] == "parent"
    assert result["mode"] == "deep_search"
    assert result["use_existing_sources_only"] is False
    assert result["followup_job"] == {"job_id": "child"}
    payload = captured["payload"]
    assert payload.query == "q"
    assert payload.mode == "deep"
    assert payload.depth == "deep"
    assert payload.recursive_search is True
    assert payload.max_queries == 4


def test_deep_search_followup_requires_research_injection():
    with pytest.raises(NexusExecutionError):
        run_nexus_research_followup_service(
            "parent",
            SimpleNamespace(question="q", use_existing_sources_only=False),
            search_chunks=lambda _request: [],
            source_search_request_factory=RequestFactory(),
        )


def test_deep_search_followup_records_parent_link_event_after_child_job_starts():
    events = []

    def run_research(payload):
        return {"job_id": "child", "job": {"job_id": "child"}, "queries": [payload.query]}

    result = run_nexus_research_followup_service(
        "parent",
        SimpleNamespace(question="q", use_existing_sources_only=False, max_iterations=1),
        search_chunks=lambda _request: [],
        source_search_request_factory=RequestFactory(),
        run_research_async=run_research,
        append_followup_parent_event=lambda child_id, payload: events.append((child_id, payload)),
    )

    assert result["job_id"] == "child"
    assert events == [("child", {"parent_job_id": "parent", "question": "q", "mode": "deep_search"})]
