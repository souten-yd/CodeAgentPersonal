from __future__ import annotations

from app.api.nexus import NexusResearchRunRequest
from app.nexus import research_api
from app.nexus.research_api import ResearchRunRequest


def _field_names(model_type):
    if hasattr(model_type, "model_fields"):
        return set(model_type.model_fields)
    return set(model_type.__fields__)


def test_nexus_research_run_request_has_adaptive_retrieval_fields():
    fields = _field_names(NexusResearchRunRequest)
    required = {
        "target_candidate_count",
        "target_valid_source_count",
        "target_evidence_count",
        "target_high_quality_source_count",
        "target_official_source_count",
        "target_pdf_source_count",
        "max_retrieval_rounds",
        "adaptive_retrieval_enabled",
        "replenishment_enabled",
        "target_replacement_ratio",
        "max_replenishment_rounds",
        "max_replenishment_candidates",
        "max_replenishment_downloads",
        "min_valid_source_count",
        "min_evidence_count",
        "source_profile",
        "news_budget",
    }
    assert required.issubset(fields)


def test_research_run_request_and_nexus_research_run_request_share_core_fields():
    api_fields = _field_names(NexusResearchRunRequest)
    run_fields = _field_names(ResearchRunRequest)
    core = {
        "target_candidate_count",
        "target_valid_source_count",
        "target_evidence_count",
        "target_high_quality_source_count",
        "target_official_source_count",
        "target_pdf_source_count",
        "max_retrieval_rounds",
        "adaptive_retrieval_enabled",
        "replenishment_enabled",
        "target_replacement_ratio",
        "max_replenishment_rounds",
        "max_replenishment_candidates",
        "max_replenishment_downloads",
        "min_valid_source_count",
        "min_evidence_count",
        "source_profile",
        "news_budget",
    }
    assert core.issubset(run_fields)
    assert core.issubset(api_fields)


def test_nexus_research_run_api_payload_has_target_candidate_count():
    payload = NexusResearchRunRequest(query="航空機電動化の動向", source_profile="market")
    assert payload.target_candidate_count is None


def test_run_research_async_accepts_minimal_payload(monkeypatch):
    def _fake_create_job(*_args, **_kwargs):
        return None

    def _fake_get_job(_job_id):
        class _Job:
            def model_dump(self, mode="json"):
                return {"status": "queued"}

        return _Job()

    def _fake_run_research_job(*_args, **_kwargs):
        return {"job_id": "dummy"}

    class _Thread:
        def __init__(self, target, **_kwargs):
            self._target = target

        def start(self):
            self._target()

    monkeypatch.setattr(research_api, "create_job", _fake_create_job)
    monkeypatch.setattr(research_api, "get_job", _fake_get_job)
    monkeypatch.setattr(research_api, "run_research_job", _fake_run_research_job)
    monkeypatch.setattr(research_api.threading, "Thread", _Thread)

    result = research_api.run_research_async(ResearchRunRequest(query="test"))
    assert result["job_id"].startswith("research_")


