"""TFG-12 operational evaluation — Twin gate wired into the live codegen orchestrator.

Exercises the real orchestrator (with fake sub-services) to prove:

- under the default active mode, every run attaches engaged Twin evidence and normal runs
  are NOT blocked (the blocking gate only fires on a genuine prerequisite);
- when the prerequisite fails (active engaged but no shadow evidence), the run stops with
  a clean blocked_safety_review and the twin gate reason;
- ATLAS_TWIN_PIPELINE_MODE=off fully reverts the seam (advisory off, never blocks);
- ATLAS_TWIN_GATE_BLOCKING=off keeps active evidence but disables blocking.
"""
from __future__ import annotations

from pathlib import Path

import agent.atlas_autonomous_codegen_orchestrator_service as orch_mod
from agent.atlas_autonomous_codegen_orchestrator_schema import AtlasAutonomousCodegenRequest
from agent.atlas_autonomous_codegen_orchestrator_service import AtlasAutonomousCodegenOrchestratorService
from agent.atlas_journal import AtlasJournal
from agent.atlas_multi_item_autopilot_schema import (
    AtlasAutopilotItemResult,
    AtlasMultiItemAutopilotRequest,
    AtlasMultiItemAutopilotResult,
)
from agent.atlas_patch_proposal_schema import AtlasPatchProposalResult
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage


def _item(item_id="i1"):
    return AtlasPlanItem(
        item_id=item_id, pool_id="pool_1", title=f"Item {item_id}", goal=f"Do {item_id}",
        item_type="implementation", status="ready", risk_level="low",
        target_files=[f"src/{item_id}.py"], metadata={"action_type": "create"},
    )


def _pool():
    return AtlasPlanPool(pool_id="pool_1", root_goal="Goal", project_path="/tmp/proj",
                         status="ready", items=[_item()], metadata={})


class _FakeProposal:
    def __init__(self, storage):
        self.storage = storage

    def propose_for_item(self, request):
        pool = self.storage.load_pool(request.pool_id)
        item = pool.get_item(request.item_id)
        if item is not None:
            item.metadata["proposed_content"] = f"# generated {request.item_id}\n"
            self.storage.save_pool(pool)
        return AtlasPatchProposalResult(
            pool_id=request.pool_id, item_id=request.item_id, run_id=request.run_id,
            status="proposed",
            metadata={"patch_content_available": True,
                      "patch_generation": {"run_id": request.run_id, "state": "succeeded",
                                           "outcome": "success", "patch_content_available": True}},
        )


class _FakeAutopilot:
    def run(self, request: AtlasMultiItemAutopilotRequest) -> AtlasMultiItemAutopilotResult:
        item_id = request.item_ids[0] if request.item_ids else "i1"
        return AtlasMultiItemAutopilotResult(
            pool_id=request.pool_id, run_id=request.run_id, autopilot_run_id="auto_test",
            policy_id=request.policy_id, status="completed", processed_count=1, completed_count=1,
            item_results=[AtlasAutopilotItemResult(
                item_id=item_id, status="completed", changed_files=[f"src/{item_id}.py"],
                verification_result={"status": "passed"},
                metadata={"bounded_retry_result": {"status": "not_needed"}})],
            created_at="2026-06-01T00:00:00+00:00",
        )


def _svc(tmp_path: Path):
    storage = AtlasPlanPoolStorage(tmp_path)
    storage.save_pool(_pool())
    journal = AtlasJournal(tmp_path, workspace_id="default")
    return AtlasAutonomousCodegenOrchestratorService(
        storage=storage, journal=journal,
        patch_proposal_service=_FakeProposal(storage),
        multi_item_autopilot_service=_FakeAutopilot(),
    )


def _request():
    return AtlasAutonomousCodegenRequest(pool_id="pool_1", user_requirement="add feature",
                                         project_path="/tmp/proj")


def test_default_active_attaches_engaged_evidence_without_blocking(tmp_path, monkeypatch):
    monkeypatch.delenv("ATLAS_TWIN_PIPELINE_MODE", raising=False)
    monkeypatch.delenv("ATLAS_TWIN_GATE_BLOCKING", raising=False)
    out = _svc(tmp_path).run(_request())
    tcp = out.metadata.get("twin_control_plane")
    assert tcp["mode"] == "active"
    assert tcp["engaged"] is True
    assert tcp["gate_blocking_enabled"] is True
    assert tcp["gate_blocked"] is False
    # Normal run proceeds past the twin gate.
    assert out.status != "blocked_safety_review" or out.stop_reason != "twin_gate_requires_shadow_evidence"


def test_twin_gate_blocks_when_prerequisite_fails(tmp_path, monkeypatch):
    monkeypatch.delenv("ATLAS_TWIN_PIPELINE_MODE", raising=False)
    monkeypatch.delenv("ATLAS_TWIN_GATE_BLOCKING", raising=False)

    # Force the genuine prerequisite failure: active engaged path with no shadow evidence.
    def fake_evidence(**kwargs):
        return {"mode": "active", "engaged": False, "available": True,
                "advisory": True, "requires_shadow_evidence": True}

    monkeypatch.setattr(orch_mod, "build_twin_pipeline_evidence", fake_evidence)
    out = _svc(tmp_path).run(_request())
    assert out.status == "blocked_safety_review"
    assert out.stop_reason == "twin_gate_requires_shadow_evidence"
    assert out.metadata["twin_control_plane"]["gate_blocked"] is True


def test_off_mode_reverts_seam(tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_TWIN_PIPELINE_MODE", "off")
    out = _svc(tmp_path).run(_request())
    tcp = out.metadata.get("twin_control_plane")
    assert tcp["mode"] == "off"
    assert tcp["engaged"] is False
    assert tcp.get("gate_blocked") is False


def test_blocking_can_be_disabled_while_active(tmp_path, monkeypatch):
    monkeypatch.delenv("ATLAS_TWIN_PIPELINE_MODE", raising=False)
    monkeypatch.setenv("ATLAS_TWIN_GATE_BLOCKING", "off")

    def fake_evidence(**kwargs):
        return {"mode": "active", "engaged": False, "available": True,
                "advisory": True, "requires_shadow_evidence": True}

    monkeypatch.setattr(orch_mod, "build_twin_pipeline_evidence", fake_evidence)
    out = _svc(tmp_path).run(_request())
    # Blocking disabled: the prerequisite failure is recorded but does not stop the run.
    assert out.stop_reason != "twin_gate_requires_shadow_evidence"
    assert out.metadata["twin_control_plane"]["gate_blocked"] is False


def test_post_apply_persists_proof_ledger_entry(tmp_path, monkeypatch):
    monkeypatch.delenv("ATLAS_TWIN_PIPELINE_MODE", raising=False)
    svc = _svc(tmp_path)
    out = svc.run(_request())
    # The post-apply gate ran and a durable ledger entry was written under data_root.
    from agent.twin_control_plane.proof_ledger import ProofLedgerStore
    store = ProofLedgerStore(tmp_path / "twin_control_plane" / "proof_ledger")
    entries = store.load().entries
    assert entries, "expected a durable proof ledger entry"
    assert out.metadata["twin_control_plane"]["post_apply"]["ran"] is True


def test_llm_usage_accumulates_and_is_reported(tmp_path, monkeypatch):
    monkeypatch.delenv("ATLAS_TWIN_PIPELINE_MODE", raising=False)
    svc = _svc(tmp_path)
    # Simulate the adapter's on_usage callback firing for two model calls.
    svc.accumulate_llm_usage({"prompt_tokens": 100, "completion_tokens": 40, "total_tokens": 140,
                              "thinking_tokens": 10, "output_tokens": 30})
    svc.accumulate_llm_usage({"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70,
                              "thinking_tokens": 0, "output_tokens": 20})
    out = svc.run(_request())
    usage = out.metadata.get("llm_usage") or {}
    assert usage["prompt_tokens"] == 150
    assert usage["thinking_tokens"] == 10 and usage["output_tokens"] == 50
    assert usage["total_tokens"] == 210 and usage["calls"] == 2
