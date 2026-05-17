from pathlib import Path

from agent.atlas_pipeline_runner import AtlasPipelineRunner

from agent.atlas_autopilot_policy import AtlasAutopilotPolicyGate
from agent.atlas_autopilot_policy_schema import AtlasPolicyEvaluation


class AllowPolicyGate(AtlasAutopilotPolicyGate):
    def evaluate_pool(self, pool):
        return AtlasPolicyEvaluation(evaluation_id='pool_allow', scope='pool', decision='allow', pool_id=pool.pool_id, auto_execution_allowed=True)

    def evaluate_item(self, item, pool):
        return AtlasPolicyEvaluation(evaluation_id=f'item_allow_{item.item_id}', scope='item', decision='allow', item_id=item.item_id, pool_id=pool.pool_id, auto_execution_allowed=True)
from agent.atlas_pipeline_runner_schema import AtlasPipelineRunRequest
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage


class FakeExecutor:
    def execute_plan_item_dry_run(self, item, pool):
        return {"dry_run": True, "run_id": f"run_{item.item_id}"}


def make_item(item_id: str, status: str = "ready", depends_on=None):
    return AtlasPlanItem(item_id=item_id, pool_id="pool_1", title=item_id, goal=item_id, status=status, depends_on=depends_on or [])


def make_storage(tmp_path: Path, pool: AtlasPlanPool) -> AtlasPlanPoolStorage:
    storage = AtlasPlanPoolStorage(tmp_path)
    storage.save_pool(pool)
    return storage


def test_pipeline_does_not_complete_when_queued_items_remain(tmp_path: Path) -> None:
    items = [make_item("item_1", "ready")] + [make_item(f"item_{i}", "queued", ["missing_dep"]) for i in range(2, 6)]
    pool = AtlasPlanPool(pool_id="pool_1", root_goal="g", status="ready", items=items)
    storage = make_storage(tmp_path, pool)
    state = AtlasPipelineRunner(storage=storage, implementation_executor=FakeExecutor(), policy_gate=AllowPolicyGate()).run_dry_run(AtlasPipelineRunRequest(pool_id="pool_1"))
    loaded = storage.load_pool("pool_1")
    assert state.status != "completed"
    assert loaded.status != "completed"
    assert "no_ready_items_remaining" in state.warnings
    assert state.metadata["total_items"] == 5
    assert state.metadata["completed_count"] == 1
    assert state.metadata["queued_count"] >= 1
    assert any(event.event_type == "pipeline_waiting" for event in state.events)


def test_dependency_alias_step_id_resolution() -> None:
    pool = AtlasPlanPool(pool_id="p", root_goal="g", items=[
        make_item("item_alpha", "ready"),
        make_item("item_beta", "ready", ["step_1"]),
    ], completed_item_ids=["item_alpha"])
    ready = pool.get_ready_items()
    ids = [i.item_id for i in ready]
    assert "item_beta" in ids


def test_queued_item_with_step_alias_dependency_runs_after_parent_completed(tmp_path: Path) -> None:
    items = [
        make_item("item_alpha", "ready"),
        make_item("item_beta", "queued", ["step_1"]),
        make_item("item_gamma", "queued", ["step_2"]),
    ]
    pool = AtlasPlanPool(pool_id="pool_1", root_goal="g", status="ready", items=items)
    storage = make_storage(tmp_path, pool)

    state = AtlasPipelineRunner(
        storage=storage,
        implementation_executor=FakeExecutor(),
        policy_gate=AllowPolicyGate(),
    ).run_dry_run(AtlasPipelineRunRequest(pool_id="pool_1"))
    loaded = storage.load_pool("pool_1")

    assert state.status == "completed"
    assert loaded.status == "completed"
    assert len(state.completed_item_ids) == 3
    assert any(event.event_type == "pipeline_completed" for event in state.events)
    assert "no_ready_items_remaining" not in state.warnings


def test_dependency_chain_with_queued_items_runs_in_order(tmp_path: Path) -> None:
    items = [
        make_item("item_1", "ready"),
        make_item("item_2", "queued", ["step_1"]),
        make_item("item_3", "queued", ["step_2"]),
        make_item("item_4", "queued", ["step_3"]),
        make_item("item_5", "queued", ["step_4"]),
    ]
    pool = AtlasPlanPool(pool_id="pool_1", root_goal="g", status="ready", items=items)
    storage = make_storage(tmp_path, pool)
    state = AtlasPipelineRunner(storage=storage, implementation_executor=FakeExecutor(), policy_gate=AllowPolicyGate()).run_dry_run(
        AtlasPipelineRunRequest(pool_id="pool_1")
    )
    loaded = storage.load_pool("pool_1")

    assert state.status == "completed"
    assert loaded.status == "completed"
    assert len(state.completed_item_ids) == 5
    completed_event_ids = [event.item_id for event in state.events if event.event_type == "item_completed"]
    assert completed_event_ids == ["item_1", "item_2", "item_3", "item_4", "item_5"]
    assert any(event.event_type == "pipeline_completed" for event in state.events)


def test_unresolved_queued_dependency_waits_not_completed(tmp_path: Path) -> None:
    items = [make_item("item_1", "ready"), make_item("item_2", "queued", ["missing_dep"])]
    pool = AtlasPlanPool(pool_id="pool_1", root_goal="g", status="ready", items=items)
    storage = make_storage(tmp_path, pool)
    state = AtlasPipelineRunner(storage=storage, implementation_executor=FakeExecutor(), policy_gate=AllowPolicyGate()).run_dry_run(
        AtlasPipelineRunRequest(pool_id="pool_1")
    )
    loaded = storage.load_pool("pool_1")

    assert state.status == "paused"
    assert loaded.status == "dependency_waiting"
    assert "item_1" in state.completed_item_ids
    item_2 = loaded.get_item("item_2")
    assert item_2 is not None
    assert item_2.status == "queued"
    assert "no_ready_items_remaining" in state.warnings
    assert any(event.event_type == "pipeline_waiting" for event in state.events)
