"""Part A2 + Part C — cross-run Twin learning, with genuine negative controls.

Drives the real orchestrator (fake sub-services) twice against the same data_root and
proves: a non-accepted run feeds the durable Anti-Pattern memory and the NEXT run's
advisory hints reflect it; an accepted run adds no false guardrail.
"""
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
from agent.twin_control_plane.anti_pattern_memory import AntiPatternMemoryStore, guardrail_hints


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
    def __init__(self, verification_status="passed"):
        self.verification_status = verification_status

    def run(self, request: AtlasMultiItemAutopilotRequest) -> AtlasMultiItemAutopilotResult:
        item_id = request.item_ids[0] if request.item_ids else "i1"
        return AtlasMultiItemAutopilotResult(
            pool_id=request.pool_id, run_id=request.run_id, autopilot_run_id="auto",
            policy_id=request.policy_id, status="completed", processed_count=1, completed_count=1,
            item_results=[AtlasAutopilotItemResult(
                item_id=item_id, status="completed", changed_files=[f"src/{item_id}.py"],
                verification_result={"status": self.verification_status},
                metadata={"bounded_retry_result": {"status": "not_needed"}})],
            created_at="2026-06-01T00:00:00+00:00")


def _svc(tmp_path, verification_status="passed"):
    storage = AtlasPlanPoolStorage(tmp_path)
    storage.save_pool(_pool())
    journal = AtlasJournal(tmp_path, workspace_id="default")
    return AtlasAutonomousCodegenOrchestratorService(
        storage=storage, journal=journal, patch_proposal_service=_FakeProposal(storage),
        multi_item_autopilot_service=_FakeAutopilot(verification_status), data_root=tmp_path)


def _request():
    return AtlasAutonomousCodegenRequest(pool_id="pool_1", user_requirement="add feature",
                                         project_path="/tmp/proj",
                                         metadata={"model_id": "m1"})


def _apm(tmp_path):
    return AntiPatternMemoryStore(Path(tmp_path) / "twin_control_plane" / "anti_pattern_memory").load()


def test_failed_run_grows_memory_and_changes_next_run_hints(tmp_path, monkeypatch):
    monkeypatch.delenv("ATLAS_TWIN_PIPELINE_MODE", raising=False)
    # Memory starts empty -> no hints.
    assert _apm(tmp_path).entries == []

    # Run 1: verification fails -> post-apply needs_repair -> anti-pattern recorded.
    _svc(tmp_path, verification_status="failed").run(_request())
    mem_after = _apm(tmp_path)
    assert mem_after.entries, "a failed run must grow the durable anti-pattern memory"
    hints = guardrail_hints(mem_after, model_id="m1")
    assert hints, "the next run must see evidence-backed guardrail hints"


def test_accepted_run_adds_no_false_guardrail(tmp_path, monkeypatch):
    monkeypatch.delenv("ATLAS_TWIN_PIPELINE_MODE", raising=False)
    # Run with passing verification -> accepted -> NO anti-pattern recorded.
    _svc(tmp_path, verification_status="passed").run(_request())
    assert _apm(tmp_path).entries == [], "an accepted run must not fabricate a guardrail"


def test_memory_is_injected_into_evidence_on_next_run(tmp_path, monkeypatch):
    monkeypatch.delenv("ATLAS_TWIN_PIPELINE_MODE", raising=False)
    # First failed run seeds memory.
    _svc(tmp_path, verification_status="failed").run(_request())
    # Second run loads the memory and surfaces advisory hint counts in evidence.
    out = _svc(tmp_path, verification_status="passed").run(_request())
    tcp = out.metadata.get("twin_control_plane") or {}
    advisory = tcp.get("advisory_context") or {}
    assert advisory.get("hint_count", 0) >= 1, "prior-run guardrails must be injected into the next run"


def test_accepted_run_persists_golden_patch_for_next_run(tmp_path, monkeypatch):
    monkeypatch.delenv("ATLAS_TWIN_PIPELINE_MODE", raising=False)
    # Force an accepted post-apply by supplying twin revisions via build-project Twin is heavy;
    # instead monkeypatch the gate to report accepted so we exercise golden-patch persistence.
    import agent.atlas_autonomous_codegen_orchestrator_service as om
    real = om.evaluate_twin_post_apply

    def accepted(**kw):
        r = real(**kw)
        r["decision"] = "accepted"; r["accepted"] = True
        r["repair_reasons"] = []; r["blocked_reasons"] = []
        return r

    monkeypatch.setattr(om, "evaluate_twin_post_apply", accepted)
    _svc(tmp_path, verification_status="passed").run(_request())
    from agent.model_forge.golden_patch_retrieval import GoldenPatchStore
    from pathlib import Path
    index = GoldenPatchStore(Path(tmp_path) / "twin_control_plane" / "golden_patches").load_index()
    assert len(index) >= 1, "an accepted run must persist a durable golden patch"
