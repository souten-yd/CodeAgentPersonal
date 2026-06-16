"""R1 — a Twin gate NG drives feedback+regeneration, it does not stop the run."""
from __future__ import annotations

from pathlib import Path

import agent.atlas_autonomous_codegen_orchestrator_service as orch_mod
from agent.atlas_autonomous_codegen_orchestrator_schema import AtlasAutonomousCodegenRequest
from agent.atlas_autonomous_codegen_orchestrator_service import AtlasAutonomousCodegenOrchestratorService
from agent.atlas_journal import AtlasJournal
from agent.atlas_multi_item_autopilot_schema import (
    AtlasAutopilotItemResult, AtlasMultiItemAutopilotRequest, AtlasMultiItemAutopilotResult,
)
from agent.atlas_patch_proposal_schema import AtlasPatchProposalResult
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage


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
    def __init__(self, statuses):
        # verification_result statuses to return on successive runs
        self.statuses = list(statuses)
        self.calls = 0

    def run(self, request: AtlasMultiItemAutopilotRequest) -> AtlasMultiItemAutopilotResult:
        st = self.statuses[min(self.calls, len(self.statuses) - 1)]
        self.calls += 1
        item_id = request.item_ids[0] if request.item_ids else "i1"
        return AtlasMultiItemAutopilotResult(
            pool_id=request.pool_id, run_id=request.run_id, autopilot_run_id=f"auto{self.calls}",
            policy_id=request.policy_id, status="completed", processed_count=1, completed_count=1,
            item_results=[AtlasAutopilotItemResult(
                item_id=item_id, status="completed", changed_files=[f"src/{item_id}.py"],
                verification_result={"status": st},
                metadata={"bounded_retry_result": {"status": "not_needed"}})],
            created_at="2026-06-01T00:00:00+00:00")


def _svc(tmp_path, autopilot):
    storage = AtlasPlanPoolStorage(tmp_path)
    storage.save_pool(_pool())
    journal = AtlasJournal(tmp_path, workspace_id="default")
    return AtlasAutonomousCodegenOrchestratorService(
        storage=storage, journal=journal, patch_proposal_service=_FakeProposal(storage),
        multi_item_autopilot_service=autopilot, data_root=tmp_path)


def _request(max_retries=2):
    return AtlasAutonomousCodegenRequest(pool_id="pool_1", user_requirement="add feature",
                                         project_path="/tmp/proj", max_retries=max_retries,
                                         metadata={"model_id": "m1"})


def test_needs_repair_regenerates_and_does_not_stop(tmp_path, monkeypatch):
    # First pass fails verification (-> needs_repair); regeneration passes -> run completes.
    monkeypatch.delenv("ATLAS_TWIN_PIPELINE_MODE", raising=False)
    autopilot = _FakeAutopilot(statuses=["failed", "passed"])
    out = _svc(tmp_path, autopilot).run(_request())
    assert out.status != "blocked_safety_review"           # did NOT stop on the Twin NG
    assert autopilot.calls >= 2                              # regenerated at least once
    assert out.metadata.get("twin_repair_attempts")         # repair feedback loop recorded


def test_hard_boundary_regenerates_then_blocks_if_persistent(tmp_path, monkeypatch):
    # A persistent hard boundary (Contract Sentinel) survives the bounded repair -> blocks.
    monkeypatch.delenv("ATLAS_TWIN_PIPELINE_MODE", raising=False)
    from agent.twin_control_plane.contract_sentinel import ContractFinding, ContractSentinelReport
    import agent.twin_control_plane.pipeline_integration as pintg
    real = pintg.evaluate_twin_post_apply

    def always_hard_block(**kw):
        kw["contract_sentinel"] = ContractSentinelReport(
            report_id="cs", accepted=False, blocked=True,
            findings=[ContractFinding(finding_id="contract.remote_publication_requires_approval",
                                      severity="hard", status="blocked", message="remote")])
        return real(**kw)

    monkeypatch.setattr(orch_mod, "evaluate_twin_post_apply", always_hard_block)
    autopilot = _FakeAutopilot(statuses=["passed"])
    out = _svc(tmp_path, autopilot).run(_request(max_retries=2))
    # It tried to repair (regenerated) before blocking as a last resort.
    assert out.metadata.get("twin_repair_attempts")
    assert out.status == "blocked_safety_review"
    assert out.stop_reason == "twin_post_apply_hard_boundary"


def test_clean_run_has_no_repair_loop(tmp_path, monkeypatch):
    monkeypatch.delenv("ATLAS_TWIN_PIPELINE_MODE", raising=False)
    autopilot = _FakeAutopilot(statuses=["passed"])
    out = _svc(tmp_path, autopilot).run(_request())
    assert out.status != "blocked_safety_review"
    assert out.metadata.get("twin_repair_attempts") in (None, [])
