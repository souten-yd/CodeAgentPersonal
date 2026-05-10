from types import SimpleNamespace

from app.nexus import research_api


def _legacy_payload_without_source_profile():
    return SimpleNamespace(
        query="legacy payload",
        project="default",
        mode="standard",
        depth=None,
        max_queries=None,
        max_results_per_query=None,
        max_sources=None,
        max_downloads=None,
        max_download_mb=None,
        max_total_download_mb=None,
        scope=None,
        language=None,
        manual_urls=None,
        prefer_pdf=True,
        official_first=True,
        download_timeout_sec=None,
        continue_on_download_error=True,
        recursive_search=False,
        max_iterations=1,
        max_followup_queries=4,
        confidence_threshold=0.75,
        stop_when_sufficient=True,
    )


def test_run_research_async_accepts_legacy_payload_without_source_profile(monkeypatch):
    captured = {}

    class CapturingResearchAgentInput:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    class NoopThread:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def start(self):
            return None

    monkeypatch.setattr(research_api, "ResearchAgentInput", CapturingResearchAgentInput)
    monkeypatch.setattr(research_api, "get_job", lambda _job_id: None)
    monkeypatch.setattr(research_api, "create_job", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        research_api,
        "get_research_job",
        lambda job_id: {"job_id": job_id, "job": {"status": "queued"}},
    )
    monkeypatch.setattr(research_api.threading, "Thread", NoopThread)

    response = research_api.run_research_async(_legacy_payload_without_source_profile())

    assert response["job"]["status"] == "queued"
    assert captured["source_profile"] == "web"
    assert captured["news_budget"] is None
