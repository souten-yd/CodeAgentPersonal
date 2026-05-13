from app.api.nexus import NexusResearchRunRequest
from app.nexus import research_api
from app.nexus.research_api import ResearchRunRequest


def _exhaustive_ui_payload() -> dict:
    return {
        "query": "exhaustive topic",
        "depth": "exhaustive",
        "max_sources": 300,
        "max_downloads": 200,
        "max_total_download_mb": 4096,
        "max_followup_queries": 12,
        "target_evidence_count": 340,
    }


def test_nexus_research_run_request_accepts_exhaustive_ui_payload():
    payload = NexusResearchRunRequest(**_exhaustive_ui_payload())
    assert payload.max_sources == 300
    assert payload.max_downloads == 200
    assert payload.max_total_download_mb == 4096
    assert payload.max_followup_queries == 12
    assert payload.target_evidence_count == 340


def test_research_run_request_accepts_exhaustive_ui_payload():
    payload = ResearchRunRequest(**_exhaustive_ui_payload())
    assert payload.max_sources == 300
    assert payload.max_downloads == 200
    assert payload.max_total_download_mb == 4096
    assert payload.max_followup_queries == 12
    assert payload.target_evidence_count == 340


def test_research_run_request_rejects_extreme_total_download_limit():
    try:
        ResearchRunRequest(query="x", max_total_download_mb=999999)
    except Exception as exc:  # pydantic validation error
        assert "max_total_download_mb" in str(exc)
    else:
        raise AssertionError("expected validation error")


def test_run_research_async_passes_max_replenishment_downloads(monkeypatch):
    captured = {}

    def fake_create_job(*args, **kwargs):
        return None

    def fake_get_job(job_id):
        class _Job:
            def model_dump(self, mode="json"):
                return {"job_id": job_id, "status": "queued"}

        return _Job()

    def fake_thread(target, name=None, daemon=None):
        class _Thread:
            def start(self):
                target()

        return _Thread()

    def fake_run_research_job(agent_input, job_id=None):
        captured["agent_input"] = agent_input
        return {"job_id": job_id or "jid"}

    monkeypatch.setattr(research_api, "create_job", fake_create_job)
    monkeypatch.setattr(research_api, "get_job", fake_get_job)
    monkeypatch.setattr(research_api.threading, "Thread", fake_thread)
    monkeypatch.setattr(research_api, "run_research_job", fake_run_research_job)

    research_api.run_research_async(
        ResearchRunRequest(
            query="test",
            max_replenishment_downloads=321,
        )
    )

    assert captured["agent_input"].max_replenishment_downloads == 321
