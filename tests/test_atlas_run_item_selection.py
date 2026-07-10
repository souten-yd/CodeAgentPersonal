from __future__ import annotations

from pathlib import Path

import pytest

from agent.atlas_journal import AtlasJournal
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_run_orchestrator import AtlasRunOrchestrator, AtlasRunOrchestratorCallbacks, AtlasRunOrchestratorRequest
from agent.atlas_run_schema import AtlasRunState
from agent.atlas_run_selection import select_run_items
from agent.atlas_run_store import AtlasRunStore


def _item(item_id: str, *, status: str = "ready", target_file: str = "app.py") -> AtlasPlanItem:
    return AtlasPlanItem(
        item_id=item_id,
        pool_id="pool_cs10",
        title=item_id,
        goal=f"update {item_id}",
        item_type="implementation",
        status=status,
        risk_level="low",
        target_files=[target_file],
        metadata={},
    )


def _pool(items: list[AtlasPlanItem] | None = None, *, completed: list[str] | None = None) -> AtlasPlanPool:
    return AtlasPlanPool(
        pool_id="pool_cs10",
        root_goal="update app",
        project_path="",
        status="ready",
        items=items or [_item("item_1"), _item("item_2")],
        completed_item_ids=list(completed or []),
    )


def test_select_run_items_fresh_uses_runnable_pool_order() -> None:
    pool = _pool([_item("item_1"), _item("item_blocked", status="blocked"), _item("item_2")])
    state = AtlasRunState(run_id="run_cs10", pool_id=pool.pool_id)

    assert select_run_items(pool, state, "fresh") == ["item_1", "item_2"]


def test_select_run_items_resume_skips_run_and_pool_completed_items() -> None:
    pool = _pool([_item("item_1"), _item("item_2"), _item("item_3")], completed=["item_2"])
    state = AtlasRunState(run_id="run_cs10", pool_id=pool.pool_id, completed_item_ids=["item_1"])

    assert select_run_items(pool, state, "resume") == ["item_3"]


def test_select_run_items_rerun_can_select_completed_items_after_state_reset() -> None:
    pool = _pool([_item("item_1", status="completed"), _item("item_2")], completed=["item_1"])
    state = AtlasRunState(run_id="run_cs10", pool_id=pool.pool_id, completed_item_ids=["item_1"])

    assert select_run_items(pool, state, "rerun") == ["item_1", "item_2"]


def test_select_run_items_rejects_explicit_blocked_item() -> None:
    pool = _pool([_item("item_1", status="blocked")])
    state = AtlasRunState(run_id="run_cs10", pool_id=pool.pool_id)

    with pytest.raises(ValueError, match="item_not_runnable:item_1:blocked"):
        select_run_items(pool, state, "fresh", requested_item_id="item_1")


def test_select_run_items_resume_retries_failed_and_blocked_items() -> None:
    # Reproduces a real bug: "resume" is supposed to be how a fully-autonomous loop keeps going
    # after a run stops on an item -- but failed/blocked items were excluded from the runnable
    # status set for every mode, so resume silently skipped past exactly the item it needed to
    # retry and jumped ahead to the next one, abandoning the stuck item until a human noticed and
    # manually re-triggered it. "fresh" mode must still exclude them (no reason a *fresh* run
    # would even select a failed item), but "resume" must pick them back up.
    pool = _pool([_item("item_1", status="failed"), _item("item_2", status="blocked"), _item("item_3")])
    state = AtlasRunState(run_id="run_cs10", pool_id=pool.pool_id)

    assert select_run_items(pool, state, "resume") == ["item_1", "item_2", "item_3"]
    assert select_run_items(pool, state, "fresh") == ["item_3"]


def test_select_run_items_resume_can_explicitly_target_a_failed_item() -> None:
    pool = _pool([_item("item_1", status="failed")])
    state = AtlasRunState(run_id="run_cs10", pool_id=pool.pool_id)

    assert select_run_items(pool, state, "resume", requested_item_id="item_1") == ["item_1"]


def test_run_orchestrator_selects_items_without_client_item_ids(tmp_path: Path) -> None:
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
    pool = _pool([_item("item_1", target_file="app.py"), _item("item_2", target_file="app.py")])
    storage = AtlasPlanPoolStorage(tmp_path)
    storage.save_pool(pool)
    journal = AtlasJournal(tmp_path, workspace_id="default")
    journal.save_plan_pool(pool)
    run_store = AtlasRunStore(tmp_path)
    run_store.create_run(pool_id=pool.pool_id, workspace_id="default", run_id="run_cs10")
    orchestrator = AtlasRunOrchestrator(run_store=run_store, plan_storage=storage, journal=journal, callbacks=callbacks)

    state = orchestrator.run_items(AtlasRunOrchestratorRequest(run_id="run_cs10", pool_id=pool.pool_id, mode="fresh"))

    assert state.status == "completed"
    assert generated == ["item_1", "item_2"]
    events = run_store.read_events("run_cs10")
    selected = [event for event in events if event.event_type == "run_items_selected"]
    assert selected
    assert selected[-1].metadata["item_ids"] == ["item_1", "item_2"]
    assert selected[-1].metadata["selection_source"] == "backend_selection"


def test_run_orchestrator_resume_actually_executes_the_failed_item_it_selected(tmp_path: Path) -> None:
    # Reproduces a second layer of the same "resume" bug fixed in select_run_items: item selection
    # (select_run_items) correctly re-admits a "failed" item for resume, but AtlasRunOrchestrator's
    # OWN separate item-runnability gate (_blocker) still unconditionally treated "failed" as
    # not-runnable regardless of mode. Live symptom: retrying a run via the resume API selected
    # step_2 (status "failed") then immediately re-blocked on "item_not_runnable:failed" in the
    # very same call, so resume never made progress on the item it was supposed to retry.
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
    pool = _pool([_item("item_1", status="failed", target_file="app.py")])
    storage = AtlasPlanPoolStorage(tmp_path)
    storage.save_pool(pool)
    journal = AtlasJournal(tmp_path, workspace_id="default")
    journal.save_plan_pool(pool)
    run_store = AtlasRunStore(tmp_path)
    run_store.create_run(pool_id=pool.pool_id, workspace_id="default", run_id="run_cs11")

    orchestrator = AtlasRunOrchestrator(run_store=run_store, plan_storage=storage, journal=journal, callbacks=callbacks)
    state = orchestrator.run_items(AtlasRunOrchestratorRequest(run_id="run_cs11", pool_id=pool.pool_id, mode="resume"))

    assert generated == ["item_1"]
    assert state.status == "completed"
    assert state.block_reason != "item_not_runnable:failed"
