from pathlib import Path

import pytest

from agent.atlas_approval_gate import AtlasApprovalGate
from agent.atlas_autopilot_policy import AtlasAutopilotPolicyGate
from agent.atlas_autopilot_policy_schema import AtlasPolicyEvaluation
from agent.atlas_pipeline_runner import AtlasPipelineRunner
from agent.atlas_pipeline_runner_schema import AtlasPipelineRunRequest
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "agent" / "atlas_pipeline_runner.py"


class ItemApprovalPolicyGate(AtlasAutopilotPolicyGate):
    def evaluate_pool(self, pool: AtlasPlanPool) -> AtlasPolicyEvaluation:
        return AtlasPolicyEvaluation(
            evaluation_id="eval_pool_allow",
            scope="pool",
            decision="allow",
            pool_id=pool.pool_id,
            auto_execution_allowed=True,
        )

    def evaluate_item(self, item: AtlasPlanItem, pool: AtlasPlanPool) -> AtlasPolicyEvaluation:
        return AtlasPolicyEvaluation(
            evaluation_id=f"eval_{item.item_id}",
            scope="item",
            decision="require_approval",
            item_id=item.item_id,
            pool_id=pool.pool_id,
            risk_level="high",
            reasons=["high risk item requires approval"],
            categories=["high_risk"],
            requires_user_confirmation=True,
        )


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


def test_pipeline_requests_approval_when_item_requires_approval(tmp_path: Path) -> None:
    executor = FakeExecutor()
    approval_gate = AtlasApprovalGate()
    storage = make_storage(tmp_path, make_pool([make_item("item_1", risk_level="high")]))

    state = AtlasPipelineRunner(
        storage=storage,
        policy_gate=ItemApprovalPolicyGate(),
        implementation_executor=executor,
        approval_gate=approval_gate,
    ).run_dry_run(AtlasPipelineRunRequest(pool_id="pool_1"))
    loaded = storage.load_pool("pool_1")
    item = loaded.get_item("item_1")
    pending_records = approval_gate.find_records(scope="item", pool_id="pool_1", item_id="item_1", status="pending")

    assert state.status == "paused"
    assert len(pending_records) == 1
    assert item is not None
    assert item.status == "approval_required"
    assert item.approval_id == pending_records[0].approval_id
    assert state.item_results[0].warnings == [f"approval_id:{pending_records[0].approval_id}"]
    assert executor.calls == []


def test_pipeline_without_approval_gate_still_pauses_on_require_approval(tmp_path: Path) -> None:
    executor = FakeExecutor()
    storage = make_storage(tmp_path, make_pool([make_item("item_1", risk_level="high")]))

    state = AtlasPipelineRunner(
        storage=storage,
        policy_gate=ItemApprovalPolicyGate(),
        implementation_executor=executor,
    ).run_dry_run(AtlasPipelineRunRequest(pool_id="pool_1"))
    loaded = storage.load_pool("pool_1")
    item = loaded.get_item("item_1")

    assert state.status == "paused"
    assert item is not None
    assert item.status == "approval_required"
    assert item.approval_id == ""
    assert executor.calls == []


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


def test_run_dry_run_does_not_call_safe_apply_adapter(tmp_path: Path) -> None:
    class FakeSafeApplyAdapter:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def apply_low_risk_item(self, **kwargs) -> dict:
            self.calls.append(kwargs)
            return {}

    adapter = FakeSafeApplyAdapter()
    storage = make_storage(tmp_path, make_pool([make_item("item_1")]))

    state = AtlasPipelineRunner(
        storage=storage,
        implementation_executor=FakeExecutor(),
        safe_apply_adapter=adapter,
    ).run_dry_run(AtlasPipelineRunRequest(pool_id="pool_1", safe_apply=True))

    assert state.status == "completed"
    assert adapter.calls == []


def test_safe_apply_item_once_delegates_to_adapter(tmp_path: Path) -> None:
    from agent.atlas_safe_apply_adapter_schema import AtlasSafeApplyResult

    class FakeSafeApplyAdapter:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def apply_low_risk_item(self, item, pool, request=None, patch_metadata=None) -> AtlasSafeApplyResult:
            self.calls.append(
                {
                    "item_id": item.item_id,
                    "pool_id": pool.pool_id,
                    "request": request,
                    "patch_metadata": patch_metadata,
                }
            )
            return AtlasSafeApplyResult(pool_id=pool.pool_id, item_id=item.item_id, status="simulated", decision="allow")

    item = make_item("item_1")
    pool = make_pool([item])
    adapter = FakeSafeApplyAdapter()
    storage = make_storage(tmp_path, pool)
    runner = AtlasPipelineRunner(storage=storage, safe_apply_adapter=adapter)

    result = runner.safe_apply_item_once(item, pool)

    assert result.status == "simulated"
    assert adapter.calls == [{"item_id": "item_1", "pool_id": "pool_1", "request": None, "patch_metadata": None}]
