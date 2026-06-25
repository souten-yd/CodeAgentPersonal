from __future__ import annotations

from pathlib import Path

from agent.atlas_journal import AtlasJournal
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_run_orchestrator import (
    AtlasRunOrchestrator,
    AtlasRunOrchestratorCallbacks,
    AtlasRunOrchestratorRequest,
)
from agent.atlas_run_store import AtlasRunStore


def _pool(*, status: str = "ready", item_status: str = "ready", metadata: dict | None = None) -> AtlasPlanPool:
    item = AtlasPlanItem(
        item_id="item_1",
        pool_id="pool_sc3",
        title="Update app",
        goal="update app",
        item_type="implementation",
        status=item_status,
        risk_level="low",
        target_files=["app.py"],
        metadata=dict(metadata or {}),
    )
    return AtlasPlanPool(
        pool_id="pool_sc3",
        root_goal="update app",
        project_path="",
        status=status,
        items=[item],
    )


def _multi_pool() -> AtlasPlanPool:
    items = [
        AtlasPlanItem(
            item_id=f"item_{idx}",
            pool_id="pool_sc3",
            title=f"Update app {idx}",
            goal=f"update app {idx}",
            item_type="implementation",
            status="ready",
            risk_level="low",
            target_files=["app.py"],
            metadata={},
        )
        for idx in (1, 2)
    ]
    return AtlasPlanPool(pool_id="pool_sc3", root_goal="update app", project_path="", status="ready", items=items)


def _orchestrator(tmp_path: Path, pool: AtlasPlanPool, callbacks: AtlasRunOrchestratorCallbacks) -> tuple[AtlasRunStore, AtlasRunOrchestrator]:
    storage = AtlasPlanPoolStorage(tmp_path)
    journal = AtlasJournal(tmp_path, workspace_id="default")
    storage.save_pool(pool)
    journal.save_plan_pool(pool)
    run_store = AtlasRunStore(tmp_path)
    state = run_store.create_run(pool_id=pool.pool_id, workspace_id="default", run_id="run_sc3", total_items=len(pool.items))
    assert state.status == "queued"
    return run_store, AtlasRunOrchestrator(run_store=run_store, plan_storage=storage, journal=journal, callbacks=callbacks)


def test_run_orchestrator_completes_one_low_risk_item(tmp_path: Path) -> None:
    calls: list[str] = []

    callbacks = AtlasRunOrchestratorCallbacks(
        approve_plan_item=lambda **_: calls.append("approve_item") or {"status": "approved"},
        generate_patch_proposal=lambda **_: calls.append("generate") or {
            "status": "proposed",
            "proposal": {"proposal_id": "proposal_1"},
        },
        approve_patch_proposal=lambda **_: calls.append("approve_proposal") or {"status": "approved"},
        apply_and_verify=lambda **_: calls.append("apply_verify") or {"status": "applied_and_verified"},
    )
    run_store, orchestrator = _orchestrator(tmp_path, _pool(), callbacks)

    state = orchestrator.run_one_item(AtlasRunOrchestratorRequest(run_id="run_sc3", pool_id="pool_sc3"))

    assert state.status == "completed"
    assert state.phase == "final_summary"
    assert state.completed_item_ids == ["item_1"]
    assert calls == ["approve_item", "generate", "approve_proposal", "apply_verify"]
    events = run_store.read_events("run_sc3")
    assert [event.event_type for event in events][-4:] == [
        "patch_proposal_completed",
        "patch_proposal_approved",
        "safe_apply_started",
        "run_completed",
    ]


def test_run_orchestrator_blocks_critical_items_before_callbacks(tmp_path: Path) -> None:
    calls: list[str] = []
    callbacks = AtlasRunOrchestratorCallbacks(
        approve_plan_item=lambda **_: calls.append("approve_item") or {},
        generate_patch_proposal=lambda **_: calls.append("generate") or {},
        approve_patch_proposal=lambda **_: calls.append("approve_proposal") or {},
        apply_and_verify=lambda **_: calls.append("apply_verify") or {},
    )
    critical = _pool(
        status="waiting_for_critical_decision",
        item_status="waiting_for_critical_decision",
        metadata={"critical_event": {"critical_event": True}},
    )
    run_store, orchestrator = _orchestrator(tmp_path, critical, callbacks)

    state = orchestrator.run_one_item(AtlasRunOrchestratorRequest(run_id="run_sc3", pool_id="pool_sc3"))

    assert state.status == "blocked"
    assert "pool_not_runnable" in state.block_reason
    assert state.requires_user_action is True
    assert calls == []
    assert run_store.read_events("run_sc3")[-1].event_type == "run_blocked"


def test_run_orchestrator_records_generation_failure_as_failed(tmp_path: Path) -> None:
    callbacks = AtlasRunOrchestratorCallbacks(
        approve_plan_item=lambda **_: {"status": "approved"},
        generate_patch_proposal=lambda **_: {"status": "failed", "errors": ["llm_failed"]},
        approve_patch_proposal=lambda **_: {"status": "approved"},
        apply_and_verify=lambda **_: {"status": "applied_and_verified"},
    )
    run_store, orchestrator = _orchestrator(tmp_path, _pool(), callbacks)

    state = orchestrator.run_one_item(AtlasRunOrchestratorRequest(run_id="run_sc3", pool_id="pool_sc3"))

    assert state.status == "failed"
    assert state.failed_item_ids == ["item_1"]
    assert "llm_failed" in state.error
    assert run_store.read_events("run_sc3")[-1].event_type == "patch_proposal_failed"


def test_run_orchestrator_runs_multiple_items_in_order(tmp_path: Path) -> None:
    generated: list[str] = []
    callbacks = AtlasRunOrchestratorCallbacks(
        approve_plan_item=lambda **_: {"status": "approved"},
        generate_patch_proposal=lambda item, **_: generated.append(item.item_id) or {
            "status": "proposed",
            "proposal": {"proposal_id": f"proposal_{item.item_id}"},
        },
        approve_patch_proposal=lambda **_: {"status": "approved"},
        apply_and_verify=lambda **_: {"status": "applied_and_verified"},
    )
    run_store, orchestrator = _orchestrator(tmp_path, _multi_pool(), callbacks)

    state = orchestrator.run_items(AtlasRunOrchestratorRequest(run_id="run_sc3", pool_id="pool_sc3", item_ids=["item_1", "item_2"]))

    assert state.status == "completed"
    assert state.completed_item_ids == ["item_1", "item_2"]
    assert generated == ["item_1", "item_2"]
    events = [event.event_type for event in run_store.read_events("run_sc3")]
    assert events.count("run_item_completed") == 2


def test_run_orchestrator_resume_skips_completed_items(tmp_path: Path) -> None:
    generated: list[str] = []
    callbacks = AtlasRunOrchestratorCallbacks(
        approve_plan_item=lambda **_: {"status": "approved"},
        generate_patch_proposal=lambda item, **_: generated.append(item.item_id) or {
            "status": "proposed",
            "proposal": {"proposal_id": f"proposal_{item.item_id}"},
        },
        approve_patch_proposal=lambda **_: {"status": "approved"},
        apply_and_verify=lambda **_: {"status": "applied_and_verified"},
    )
    run_store, orchestrator = _orchestrator(tmp_path, _multi_pool(), callbacks)
    run_store.patch_state("run_sc3", {"completed_item_ids": ["item_1"]})

    state = orchestrator.run_items(
        AtlasRunOrchestratorRequest(run_id="run_sc3", pool_id="pool_sc3", item_ids=["item_1", "item_2"], mode="resume")
    )

    assert state.status == "completed"
    assert state.completed_item_ids == ["item_1", "item_2"]
    assert generated == ["item_2"]
    assert "item_1" in state.skipped_item_ids


def test_run_orchestrator_rerun_resets_completed_items(tmp_path: Path) -> None:
    generated: list[str] = []
    callbacks = AtlasRunOrchestratorCallbacks(
        approve_plan_item=lambda **_: {"status": "approved"},
        generate_patch_proposal=lambda item, **_: generated.append(item.item_id) or {
            "status": "proposed",
            "proposal": {"proposal_id": f"proposal_{item.item_id}"},
        },
        approve_patch_proposal=lambda **_: {"status": "approved"},
        apply_and_verify=lambda **_: {"status": "applied_and_verified"},
    )
    run_store, orchestrator = _orchestrator(tmp_path, _multi_pool(), callbacks)
    run_store.patch_state("run_sc3", {"completed_item_ids": ["item_1"], "failed_item_ids": ["old_failed"]})

    state = orchestrator.run_items(
        AtlasRunOrchestratorRequest(run_id="run_sc3", pool_id="pool_sc3", item_ids=["item_1"], mode="rerun")
    )

    assert state.status == "completed"
    assert state.completed_item_ids == ["item_1"]
    assert state.failed_item_ids == []
    assert generated == ["item_1"]
    assert "run_rerun_reset" in [event.event_type for event in run_store.read_events("run_sc3")]


def test_run_orchestrator_multi_item_generation_failure_is_terminal(tmp_path: Path) -> None:
    generated: list[str] = []
    callbacks = AtlasRunOrchestratorCallbacks(
        approve_plan_item=lambda **_: {"status": "approved"},
        generate_patch_proposal=lambda item, **_: generated.append(item.item_id) or {"status": "failed", "errors": ["llm_failed"]},
        approve_patch_proposal=lambda **_: {"status": "approved"},
        apply_and_verify=lambda **_: {"status": "applied_and_verified"},
    )
    _run_store, orchestrator = _orchestrator(tmp_path, _multi_pool(), callbacks)

    state = orchestrator.run_items(AtlasRunOrchestratorRequest(run_id="run_sc3", pool_id="pool_sc3", item_ids=["item_1", "item_2"]))

    assert state.status == "failed"
    assert state.failed_item_ids == ["item_1"]
    assert state.completed_item_ids == []
    assert generated == ["item_1"]
