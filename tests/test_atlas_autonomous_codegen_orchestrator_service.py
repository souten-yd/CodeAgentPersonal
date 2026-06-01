from __future__ import annotations

from pathlib import Path

from agent.atlas_autonomous_codegen_orchestrator_schema import AtlasAutonomousCodegenRequest
from agent.atlas_autonomous_codegen_orchestrator_service import AtlasAutonomousCodegenOrchestratorService
from agent.atlas_journal import AtlasJournal
from agent.atlas_multi_item_autopilot_schema import AtlasMultiItemAutopilotRequest, AtlasMultiItemAutopilotResult
from agent.atlas_patch_proposal_schema import AtlasPatchProposalResult
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage


def _item(item_id: str, *, risk_level: str = "low", action_type: str = "create", metadata: dict | None = None) -> AtlasPlanItem:
    md = {"action_type": action_type}
    if metadata:
        md.update(metadata)
    return AtlasPlanItem(
        item_id=item_id,
        pool_id="pool_1",
        title=f"Item {item_id}",
        goal=f"Do {item_id}",
        item_type="implementation",
        status="ready",
        risk_level=risk_level,
        target_files=[f"src/{item_id}.py"],
        metadata=md,
    )


def _pool(items, *, status: str = "ready", metadata: dict | None = None) -> AtlasPlanPool:
    return AtlasPlanPool(pool_id="pool_1", root_goal="Goal", project_path="/tmp/proj", status=status, items=items, metadata=metadata or {})


def _active_envelope() -> dict:
    return {
        "envelope_id": "pre_authorized_bounded_dev_envelope",
        "status": "active",
        "bounds": {
            "allowed_paths": ["src/"],
            "blocked_paths": [".git/"],
            "max_actions_per_loop": 5,
            "max_files_changed": 5,
            "max_runtime_seconds": 60,
            "max_risk_level": "medium",
        },
    }


class FakeProposalService:
    """Fills proposed_content for the requested item (mirrors the real service persisting to pool)."""

    def __init__(self, storage: AtlasPlanPoolStorage, *, produce_content: bool = True):
        self.storage = storage
        self.produce_content = produce_content
        self.calls: list[str] = []

    def propose_for_item(self, request):
        self.calls.append(request.item_id)
        pool = self.storage.load_pool(request.pool_id)
        item = pool.get_item(request.item_id)
        available = False
        if item is not None and self.produce_content:
            item.metadata["proposed_content"] = f"# generated {request.item_id}\n"
            self.storage.save_pool(pool)
            available = True
        return AtlasPatchProposalResult(
            pool_id=request.pool_id,
            item_id=request.item_id,
            run_id=request.run_id,
            status="proposed",
            metadata={"patch_content_available": available},
            warnings=[] if available else ["patch_content_unavailable"],
        )


class FakeAutopilotService:
    def __init__(self, status: str = "completed"):
        self.status = status
        self.last_request: AtlasMultiItemAutopilotRequest | None = None

    def run(self, request: AtlasMultiItemAutopilotRequest) -> AtlasMultiItemAutopilotResult:
        self.last_request = request
        return AtlasMultiItemAutopilotResult(
            pool_id=request.pool_id,
            run_id=request.run_id,
            autopilot_run_id="auto_test",
            policy_id=request.policy_id,
            status=self.status,
            processed_count=len(request.item_ids) or 1,
            completed_count=1,
            created_at="2026-06-01T00:00:00+00:00",
        )


def _orchestrator(tmp_path: Path, pool: AtlasPlanPool, *, produce_content: bool = True, autopilot_status: str = "completed"):
    storage = AtlasPlanPoolStorage(tmp_path)
    storage.save_pool(pool)
    journal = AtlasJournal(tmp_path, workspace_id="default")
    proposal = FakeProposalService(storage, produce_content=produce_content)
    autopilot = FakeAutopilotService(status=autopilot_status)
    svc = AtlasAutonomousCodegenOrchestratorService(
        storage=storage,
        journal=journal,
        patch_proposal_service=proposal,
        multi_item_autopilot_service=autopilot,
    )
    return svc, storage, proposal, autopilot


def test_generates_missing_patch_then_applies(tmp_path: Path) -> None:
    svc, storage, proposal, autopilot = _orchestrator(tmp_path, _pool([_item("i1")]))

    out = svc.run(AtlasAutonomousCodegenRequest(pool_id="pool_1"))

    assert proposal.calls == ["i1"]  # content was missing -> generated
    assert out.generated_count == 1
    assert autopilot.last_request is not None  # apply phase ran
    assert autopilot.last_request.policy_id == "full_auto_multi_item_v1"
    assert autopilot.last_request.require_approval is False
    assert out.phase == "final_summary"
    assert out.status == "completed"
    # The pool is tagged full_autopilot so the single-item pipeline also relaxes.
    assert storage.load_pool("pool_1").automation_level == "full_autopilot"


def test_missing_project_path_stops_safely(tmp_path: Path) -> None:
    pool = _pool([_item("i1")])
    pool.project_path = ""
    svc, _storage, proposal, autopilot = _orchestrator(tmp_path, pool)

    out = svc.run(AtlasAutonomousCodegenRequest(pool_id="pool_1"))

    assert out.status == "stopped"
    assert out.phase == "understanding_goal"
    assert out.stop_reason == "missing_project_path"
    assert proposal.calls == []
    assert autopilot.last_request is None


def test_unsafe_path_stops_before_generation(tmp_path: Path) -> None:
    item = _item("i1")
    item.target_files = ["../outside.py"]
    svc, _storage, proposal, autopilot = _orchestrator(tmp_path, _pool([item]))

    out = svc.run(AtlasAutonomousCodegenRequest(pool_id="pool_1"))

    assert out.status == "stopped"
    assert out.stop_reason == "unsafe_path"
    assert proposal.calls == []
    assert autopilot.last_request is None


def test_unknown_profile_falls_back_safely_without_running(tmp_path: Path) -> None:
    svc, _storage, proposal, autopilot = _orchestrator(tmp_path, _pool([_item("i1")]))

    out = svc.run(AtlasAutonomousCodegenRequest(pool_id="pool_1", selected_profile="mystery"))

    assert out.status == "stopped"
    assert out.stop_reason == "unknown_profile_fallback"
    assert "unknown_profile_fell_back_to_review_only" in out.warnings
    assert proposal.calls == []
    assert autopilot.last_request is None


def test_autonomous_dev_agent_without_active_envelope_does_not_run(tmp_path: Path) -> None:
    svc, _storage, proposal, autopilot = _orchestrator(tmp_path, _pool([_item("i1")]))

    out = svc.run(AtlasAutonomousCodegenRequest(pool_id="pool_1", selected_profile="autonomous_dev_agent"))

    assert out.status == "stopped"
    assert out.stop_reason == "selected_profile_inactive_envelope"
    assert proposal.calls == []
    assert autopilot.last_request is None


def test_active_bounded_envelope_allows_bounded_loop(tmp_path: Path) -> None:
    svc, _storage, proposal, autopilot = _orchestrator(tmp_path, _pool([_item("i1")]))

    out = svc.run(
        AtlasAutonomousCodegenRequest(
            pool_id="pool_1",
            selected_profile="autonomous_dev_agent",
            envelope=_active_envelope(),
        )
    )

    assert out.status == "completed"
    assert proposal.calls == ["i1"]
    assert autopilot.last_request is not None


def test_self_improvement_without_strict_gate_stops(tmp_path: Path) -> None:
    svc, _storage, proposal, autopilot = _orchestrator(tmp_path, _pool([_item("i1")]))

    out = svc.run(
        AtlasAutonomousCodegenRequest(
            pool_id="pool_1",
            selected_profile="autonomous_dev_agent",
            envelope=_active_envelope(),
            self_improvement=True,
        )
    )

    assert out.status == "stopped"
    assert out.stop_reason == "self_improvement_without_strict_gate"
    assert proposal.calls == []
    assert autopilot.last_request is None


def test_does_not_regenerate_when_content_present(tmp_path: Path) -> None:
    item = _item("i1", metadata={"proposed_content": "already here\n"})
    svc, _storage, proposal, autopilot = _orchestrator(tmp_path, _pool([item]))

    out = svc.run(AtlasAutonomousCodegenRequest(pool_id="pool_1"))

    assert proposal.calls == []  # content already present -> skipped
    assert out.skipped_generation_count == 1
    assert autopilot.last_request is not None


def test_blocks_on_plan_revision_required(tmp_path: Path) -> None:
    svc, _storage, proposal, autopilot = _orchestrator(
        tmp_path, _pool([_item("i1")], metadata={"plan_revision_required": True})
    )

    out = svc.run(AtlasAutonomousCodegenRequest(pool_id="pool_1"))

    assert out.status == "blocked_safety_review"
    assert out.stop_reason == "plan_revision_required"
    assert proposal.calls == []  # never reached patch generation
    assert autopilot.last_request is None  # apply phase never ran


def test_blocks_on_approval_required_pool_status(tmp_path: Path) -> None:
    svc, _storage, _proposal, autopilot = _orchestrator(tmp_path, _pool([_item("i1")], status="approval_required"))

    out = svc.run(AtlasAutonomousCodegenRequest(pool_id="pool_1"))

    assert out.status == "blocked_safety_review"
    assert out.stop_reason == "approval_required"
    assert autopilot.last_request is None


def test_skips_patch_generation_for_critical_and_delete_items(tmp_path: Path) -> None:
    items = [
        _item("crit", risk_level="critical"),
        _item("del", action_type="delete"),
        _item("ok", risk_level="medium"),
    ]
    svc, _storage, proposal, autopilot = _orchestrator(tmp_path, _pool(items))

    out = svc.run(AtlasAutonomousCodegenRequest(pool_id="pool_1"))

    assert proposal.calls == ["ok"]  # only the applicable item gets a proposal
    assert out.skipped_generation_count == 2
    assert autopilot.last_request is not None  # apply still runs (engine hard-blocks crit/del)


def test_no_items_pool_short_circuits(tmp_path: Path) -> None:
    svc, _storage, proposal, autopilot = _orchestrator(tmp_path, _pool([]))

    out = svc.run(AtlasAutonomousCodegenRequest(pool_id="pool_1"))

    assert out.status == "no_items"
    assert proposal.calls == []
    assert autopilot.last_request is None


def test_weak_model_empty_proposal_is_not_counted(tmp_path: Path) -> None:
    svc, _storage, proposal, autopilot = _orchestrator(tmp_path, _pool([_item("i1")]), produce_content=False)

    out = svc.run(AtlasAutonomousCodegenRequest(pool_id="pool_1"))

    assert proposal.calls == ["i1"]
    assert out.generated_count == 0  # honest: no usable content produced
    assert out.proposal_results[0].patch_content_available is False
    assert autopilot.last_request is not None  # apply still runs; engine will skip uncontented items
