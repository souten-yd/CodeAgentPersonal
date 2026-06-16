"""G1 — control-plane capability profile auto-updates from production run outcomes."""
from __future__ import annotations

from pathlib import Path

from agent.atlas_autonomous_codegen_orchestrator_schema import AtlasAutonomousCodegenRequest
from agent.atlas_autonomous_codegen_orchestrator_service import AtlasAutonomousCodegenOrchestratorService
from agent.atlas_journal import AtlasJournal
from agent.atlas_multi_item_autopilot_schema import (
    AtlasAutopilotItemResult, AtlasMultiItemAutopilotRequest, AtlasMultiItemAutopilotResult,
)
from agent.atlas_patch_proposal_schema import AtlasPatchProposalResult
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.model_forge.profile_store import ProfileStore


def _pool():
    return AtlasPlanPool(pool_id="pool_1", root_goal="Goal", project_path="/tmp/proj",
                         status="ready", items=[AtlasPlanItem(
                             item_id="i1", pool_id="pool_1", title="t", goal="do",
                             item_type="implementation", status="ready", risk_level="low",
                             target_files=["src/i1.py"], metadata={"action_type": "create"})],
                         metadata={})


class _FakeProposal:
    def __init__(self, storage):
        self.storage = storage

    def propose_for_item(self, request):
        pool = self.storage.load_pool(request.pool_id)
        item = pool.get_item(request.item_id)
        if item is not None:
            item.metadata["proposed_content"] = "# gen\n"
            self.storage.save_pool(pool)
        return AtlasPatchProposalResult(
            pool_id=request.pool_id, item_id=request.item_id, run_id=request.run_id, status="proposed",
            metadata={"patch_content_available": True,
                      "patch_generation": {"run_id": request.run_id, "state": "succeeded",
                                           "outcome": "success", "patch_content_available": True}})


class _FakeAutopilot:
    def __init__(self, status="passed"):
        self.status = status

    def run(self, request: AtlasMultiItemAutopilotRequest) -> AtlasMultiItemAutopilotResult:
        item_id = request.item_ids[0] if request.item_ids else "i1"
        return AtlasMultiItemAutopilotResult(
            pool_id=request.pool_id, run_id=request.run_id, autopilot_run_id="auto",
            policy_id=request.policy_id, status="completed", processed_count=1, completed_count=1,
            item_results=[AtlasAutopilotItemResult(
                item_id=item_id, status="completed", changed_files=[f"src/{item_id}.py"],
                verification_result={"status": self.status},
                metadata={"bounded_retry_result": {"status": "not_needed"}})],
            created_at="2026-06-01T00:00:00+00:00")


def _svc(tmp_path, status="passed"):
    storage = AtlasPlanPoolStorage(tmp_path)
    storage.save_pool(_pool())
    journal = AtlasJournal(tmp_path, workspace_id="default")
    return AtlasAutonomousCodegenOrchestratorService(
        storage=storage, journal=journal, patch_proposal_service=_FakeProposal(storage),
        multi_item_autopilot_service=_FakeAutopilot(status), data_root=tmp_path)


def _request(model_id="m1"):
    md = {"model_id": model_id, "provider_id": "local"} if model_id else {}
    return AtlasAutonomousCodegenRequest(pool_id="pool_1", user_requirement="add feature",
                                         project_path="/tmp/proj", metadata=md)


def _profile(tmp_path):
    return ProfileStore(Path(tmp_path) / "model_forge" / "profiles").load_profile("local", "m1")


def test_passed_run_raises_capability_dimensions(tmp_path, monkeypatch):
    monkeypatch.delenv("ATLAS_TWIN_PIPELINE_MODE", raising=False)
    _svc(tmp_path, status="passed").run(_request())
    prof = _profile(tmp_path)
    assert prof is not None
    assert prof.dimension_scores.get("test_generation") == 1.0
    assert prof.dimension_scores.get("contract_preservation") == 1.0


def test_failed_run_lowers_test_generation(tmp_path, monkeypatch):
    monkeypatch.delenv("ATLAS_TWIN_PIPELINE_MODE", raising=False)
    _svc(tmp_path, status="failed").run(_request())
    prof = _profile(tmp_path)
    assert prof is not None
    assert prof.dimension_scores.get("test_generation") == 0.0


def test_no_model_id_records_no_profile(tmp_path, monkeypatch):
    monkeypatch.delenv("ATLAS_TWIN_PIPELINE_MODE", raising=False)
    _svc(tmp_path, status="passed").run(_request(model_id=""))
    assert _profile(tmp_path) is None  # no anonymous attribution


def test_accumulated_evidence_feeds_next_run_injection(tmp_path, monkeypatch):
    monkeypatch.delenv("ATLAS_TWIN_PIPELINE_MODE", raising=False)
    # Two failed runs -> test_generation averages low -> known weakness on the next run.
    _svc(tmp_path, status="failed").run(_request())
    out = _svc(tmp_path, status="failed").run(_request())
    tcp = out.metadata.get("twin_control_plane") or {}
    assert tcp.get("capability_profile_available") is True
    assert "test_generation" in (tcp.get("known_weaknesses") or [])
