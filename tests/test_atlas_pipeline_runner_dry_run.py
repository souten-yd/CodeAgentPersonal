from pathlib import Path

import pytest

from agent.atlas_autopilot_policy import AtlasAutopilotPolicyGate
from agent.atlas_pipeline_runner import AtlasPipelineRunner
from agent.atlas_pipeline_runner_schema import AtlasPipelineRunRequest
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "agent" / "atlas_pipeline_runner.py"


class FakeExecutor:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.calls: list[dict] = []

    def execute_plan_item_dry_run(self, item: AtlasPlanItem, pool: AtlasPlanPool) -> dict:
        self.calls.append({"item_id": item.item_id, "pool_id": pool.pool_id, "dry_run": True})
        if self.fail:
            raise RuntimeError("fake executor failed")
        return {"dry_run": True, "run_id": f"fake_run_{item.item_id}", "item_id": item.item_id}


def make_storage(tmp_path: Path, pool: AtlasPlanPool) -> AtlasPlanPoolStorage:
    storage = AtlasPlanPoolStorage(tmp_path)
    storage.save_pool(pool)
    return storage


def make_item(
    item_id: str,
    *,
    status: str = "ready",
    risk_level: str = "low",
    depends_on: list[str] | None = None,
    metadata: dict | None = None,
) -> AtlasPlanItem:
    return AtlasPlanItem(
        item_id=item_id,
        pool_id="pool_1",
        title=f"Item {item_id}",
        goal=f"Do {item_id}",
        status=status,
        risk_level=risk_level,
        depends_on=depends_on or [],
        target_files=[f"agent/{item_id}.py"],
        metadata=metadata or {},
    )


def make_pool(items: list[AtlasPlanItem]) -> AtlasPlanPool:
    return AtlasPlanPool(pool_id="pool_1", root_goal="Goal", status="ready", items=items)


def test_run_dry_run_rejects_non_dry_run_request(tmp_path: Path) -> None:
    storage = make_storage(tmp_path, make_pool([make_item("item_1")]))
    runner = AtlasPipelineRunner(storage=storage, implementation_executor=FakeExecutor())

    with pytest.raises(ValueError):
        runner.run_dry_run(AtlasPipelineRunRequest(pool_id="pool_1", dry_run=False))


def test_select_next_ready_item_returns_first_ready(tmp_path: Path) -> None:
    pool = make_pool([make_item("item_1"), make_item("item_2")])
    storage = make_storage(tmp_path, pool)
    runner = AtlasPipelineRunner(storage=storage)

    item = runner.select_next_ready_item(pool)

    assert item is not None
    assert item.item_id == "item_1"


def test_pipeline_blocks_when_pool_policy_blocks(tmp_path: Path) -> None:
    executor = FakeExecutor()
    pool = make_pool([make_item("item_1", metadata={"action_type": "delete"})])
    storage = make_storage(tmp_path, pool)

    state = AtlasPipelineRunner(storage=storage, implementation_executor=executor).run_dry_run(
        AtlasPipelineRunRequest(pool_id="pool_1")
    )

    assert state.status == "blocked"
    assert "item_1" in state.blocked_item_ids
    assert executor.calls == []
    assert any(event.event_type == "pipeline_blocked" for event in state.events)


def test_pipeline_pauses_when_pool_requires_approval(tmp_path: Path) -> None:
    executor = FakeExecutor()
    pool = make_pool([make_item("item_1", risk_level="high")])
    storage = make_storage(tmp_path, pool)

    state = AtlasPipelineRunner(storage=storage, implementation_executor=executor).run_dry_run(
        AtlasPipelineRunRequest(pool_id="pool_1")
    )

    assert state.status == "paused"
    assert state.metadata["approval_required_item_ids"] == ["item_1"]
    assert executor.calls == []
    assert any(event.event_type in {"policy_evaluated", "pipeline_paused"} for event in state.events)


def test_pipeline_dry_runs_allowed_ready_item_with_fake_executor(tmp_path: Path) -> None:
    executor = FakeExecutor()
    storage = make_storage(tmp_path, make_pool([make_item("item_1")]))

    state = AtlasPipelineRunner(storage=storage, implementation_executor=executor).run_dry_run(
        AtlasPipelineRunRequest(pool_id="pool_1")
    )
    loaded = storage.load_pool("pool_1")
    item = loaded.get_item("item_1")

    assert executor.calls == [{"item_id": "item_1", "pool_id": "pool_1", "dry_run": True}]
    assert item is not None
    assert item.status == "completed"
    assert "item_1" in loaded.completed_item_ids
    assert state.status == "completed"
    assert state.item_results[0].status == "completed"


def test_pipeline_uses_simulation_when_no_executor_provided(tmp_path: Path) -> None:
    storage = make_storage(tmp_path, make_pool([make_item("item_1")]))

    state = AtlasPipelineRunner(storage=storage, implementation_executor=None).run_dry_run(
        AtlasPipelineRunRequest(pool_id="pool_1")
    )

    assert state.status == "completed"
    assert state.item_results[0].status == "completed"
    assert state.item_results[0].dry_run_result["skipped_executor"] is True


def test_pipeline_stops_on_executor_failure(tmp_path: Path) -> None:
    executor = FakeExecutor(fail=True)
    storage = make_storage(tmp_path, make_pool([make_item("item_1"), make_item("item_2")]))

    state = AtlasPipelineRunner(storage=storage, implementation_executor=executor).run_dry_run(
        AtlasPipelineRunRequest(pool_id="pool_1")
    )
    loaded = storage.load_pool("pool_1")
    item = loaded.get_item("item_1")

    assert item is not None
    assert item.status == "failed"
    assert state.status == "failed"
    assert "item_1" in state.failed_item_ids
    assert len(executor.calls) == 1


def test_pause_after_each_item_pauses_after_one_success(tmp_path: Path) -> None:
    executor = FakeExecutor()
    storage = make_storage(tmp_path, make_pool([make_item("item_1"), make_item("item_2")]))

    state = AtlasPipelineRunner(storage=storage, implementation_executor=executor).run_dry_run(
        AtlasPipelineRunRequest(pool_id="pool_1", pause_after_each_item=True)
    )
    loaded = storage.load_pool("pool_1")
    first = loaded.get_item("item_1")
    second = loaded.get_item("item_2")

    assert state.status == "paused"
    assert first is not None and first.status == "completed"
    assert second is not None and second.status == "ready"
    assert len(executor.calls) == 1


def test_max_items_limits_processed_items(tmp_path: Path) -> None:
    executor = FakeExecutor()
    storage = make_storage(tmp_path, make_pool([make_item("item_1"), make_item("item_2")]))

    state = AtlasPipelineRunner(storage=storage, implementation_executor=executor).run_dry_run(
        AtlasPipelineRunRequest(pool_id="pool_1", max_items=1)
    )
    loaded = storage.load_pool("pool_1")
    first = loaded.get_item("item_1")
    second = loaded.get_item("item_2")

    assert state.status == "paused"
    assert "max_items_reached" in state.warnings
    assert state.metadata["max_items_reached"] is True
    assert first is not None and first.status == "completed"
    assert second is not None and second.status == "ready"
    assert len(executor.calls) == 1


def test_runner_has_no_runtime_api_or_safe_apply_side_effect_tokens() -> None:
    text = RUNNER_PATH.read_text(encoding="utf-8")

    for token in (
        "FastAPI",
        "@app.",
        "subprocess",
        "safe_apply(",
        "delete_file",
        ".unlink(",
        ".write_text(",
        "run_command(",
    ):
        assert token not in text
