from __future__ import annotations

from pathlib import Path

from agent.atlas_journal import AtlasJournal
from agent.atlas_recovery_service import AtlasRecoveryService
from agent.atlas_pipeline_runner_schema import AtlasPipelineRunState
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool


def make_pool(pool_id: str = "pool_1", status: str = "ready") -> AtlasPlanPool:
    return AtlasPlanPool(
        pool_id=pool_id,
        root_goal="Recover Atlas state",
        status=status,
        items=[
            AtlasPlanItem(
                item_id="item_1",
                pool_id=pool_id,
                title="Recover first item",
                goal="Summarize current execution",
                status="ready",
                risk_level="low",
            ),
            AtlasPlanItem(
                item_id="item_2",
                pool_id=pool_id,
                title="Recover second item",
                goal="Prepare next action",
                status="queued",
                risk_level="low",
            ),
        ],
    )


def make_state(status: str = "running") -> AtlasPipelineRunState:
    return AtlasPipelineRunState(
        run_id="run_1",
        pool_id="pool_1",
        status=status,
        current_item_id="item_2",
        completed_item_ids=["item_1"],
        failed_item_ids=["item_failed"] if status == "failed" else [],
        blocked_item_ids=[],
    )


def test_recover_latest_no_workspace(tmp_path: Path) -> None:
    recovery = AtlasRecoveryService(AtlasJournal(tmp_path, workspace_id="ws_1"))

    summary = recovery.recover_latest()

    assert summary.status == "no_workspace"
    assert summary.next_action == "Create or select an Atlas plan pool."


def test_recover_latest_no_plan_pool(tmp_path: Path) -> None:
    journal = AtlasJournal(tmp_path, workspace_id="ws_1")
    journal.workspace_dir().mkdir(parents=True)

    summary = AtlasRecoveryService(journal).recover_latest()

    assert summary.status == "no_plan_pool"
    assert summary.next_action == "Create or select an Atlas plan pool."


def test_recover_pool_without_run(tmp_path: Path) -> None:
    journal = AtlasJournal(tmp_path, workspace_id="ws_1")
    journal.save_plan_pool(make_pool())

    summary = AtlasRecoveryService(journal).recover_pool("pool_1")

    assert summary.pool_id == "pool_1"
    assert summary.total_items == 2
    assert summary.status == "ready"


def test_recover_run_with_state_and_events(tmp_path: Path) -> None:
    journal = AtlasJournal(tmp_path, workspace_id="ws_1")
    journal.save_plan_pool(make_pool())
    journal.save_pipeline_state("pool_1", make_state())
    journal.append_event("pool_1", "run_1", {"event_type": "item_completed", "message": "Item one completed"})

    summary = AtlasRecoveryService(journal).recover_run("pool_1", "run_1")

    assert summary.run_id == "run_1"
    assert summary.pool_id == "pool_1"
    assert summary.last_event_type == "item_completed"
    assert summary.last_event_message == "Item one completed"
    assert summary.completed_count == 1
    assert summary.failed_count == 0
    assert summary.total_items == 2
    assert summary.current_item_title == "Recover second item"


def test_recover_completed_run_next_action(tmp_path: Path) -> None:
    journal = AtlasJournal(tmp_path, workspace_id="ws_1")
    journal.save_plan_pool(make_pool(status="completed"))
    journal.save_pipeline_state("pool_1", make_state(status="completed"))

    summary = AtlasRecoveryService(journal).recover_run("pool_1", "run_1")

    assert summary.status == "completed"
    assert "final report" in summary.next_action
    assert "next plan pool" in summary.next_action


def test_recover_failed_run_next_action(tmp_path: Path) -> None:
    journal = AtlasJournal(tmp_path, workspace_id="ws_1")
    journal.save_plan_pool(make_pool(status="failed"))
    journal.save_pipeline_state("pool_1", make_state(status="failed"))

    summary = AtlasRecoveryService(journal).recover_run("pool_1", "run_1")

    assert summary.status == "failed"
    assert "debug loop" in summary.next_action


def test_recovery_has_no_api_ui_side_effect_tokens() -> None:
    source = Path("agent/atlas_recovery_service.py").read_text(encoding="utf-8")

    for forbidden in [
        "FastAPI",
        "@app.",
        "subprocess",
        "safe_apply",
        "run_command(",
        "delete_file",
        ".write_text(",
        ".unlink(",
    ]:
        assert forbidden not in source
