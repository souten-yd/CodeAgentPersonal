from pathlib import Path

from agent.atlas_autopilot_policy import AtlasAutopilotPolicyGate
from agent.atlas_autopilot_policy_schema import AtlasPolicyEvaluation
from agent.atlas_journal import AtlasJournal
from agent.atlas_nexus_research_adapter import AtlasNexusResearchAdapter
from agent.atlas_nexus_research_schema import AtlasNexusContextPack, AtlasNexusResearchRequest
from agent.atlas_pipeline_runner import AtlasPipelineRunner
from agent.atlas_pipeline_runner_schema import AtlasPipelineRunRequest
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "agent" / "atlas_pipeline_runner.py"


class PoolAllowItemApprovalPolicyGate(AtlasAutopilotPolicyGate):
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
            risk_level=item.risk_level,
            reasons=["high risk item requires approval"],
            categories=["high_risk"],
            requires_user_confirmation=True,
        )


class PoolAllowItemBlockPolicyGate(AtlasAutopilotPolicyGate):
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
            decision="block",
            item_id=item.item_id,
            pool_id=pool.pool_id,
            risk_level=item.risk_level,
            reasons=["delete action is forbidden by policy"],
            categories=["delete_forbidden"],
            blocked=True,
        )


class FakeExecutor:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def execute_plan_item_dry_run(self, item: AtlasPlanItem, pool: AtlasPlanPool) -> dict:
        self.calls.append({"item_id": item.item_id, "pool_id": pool.pool_id})
        return {"dry_run": True, "item_id": item.item_id}


class FakeNexusAdapter:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.request_calls: list[str] = []
        self.run_calls: list[str] = []

    def request_from_plan_item(self, item: AtlasPlanItem) -> AtlasNexusResearchRequest:
        self.request_calls.append(item.item_id)
        return AtlasNexusResearchRequest(
            pool_id=item.pool_id,
            item_id=item.item_id,
            source="planner",
            purpose="codebase_context",
            query=item.goal,
        )

    def run_research(self, request: AtlasNexusResearchRequest) -> AtlasNexusContextPack:
        self.run_calls.append(request.item_id)
        if self.fail:
            raise RuntimeError("unexpected adapter boom")
        return AtlasNexusContextPack(
            request_id=request.request_id,
            purpose=request.purpose,
            status="completed",
            summary="ok",
            confidence=0.9,
        )


class FakeNexusClient:
    def run_research(self, request: AtlasNexusResearchRequest) -> dict:
        return {
            "summary": "journal ok",
            "findings": [{"title": "journal finding", "content": "saved context"}],
            "confidence": 0.8,
        }


def make_storage(tmp_path: Path, pool: AtlasPlanPool) -> AtlasPlanPoolStorage:
    storage = AtlasPlanPoolStorage(tmp_path)
    storage.save_pool(pool)
    return storage


def make_research_item(
    item_id: str = "research_1",
    *,
    status: str = "ready",
    risk_level: str = "low",
    metadata: dict | None = None,
) -> AtlasPlanItem:
    return AtlasPlanItem(
        item_id=item_id,
        pool_id="pool_1",
        title="Research item",
        goal="Research implementation context",
        item_type="research",
        status=status,
        risk_level=risk_level,
        target_files=["agent/example.py"],
        metadata=metadata or {},
    )


def make_pool(items: list[AtlasPlanItem]) -> AtlasPlanPool:
    return AtlasPlanPool(pool_id="pool_1", root_goal="Goal", status="ready", items=items)


def test_research_item_uses_nexus_adapter_and_completes(tmp_path: Path) -> None:
    adapter = FakeNexusAdapter()
    executor = FakeExecutor()
    storage = make_storage(tmp_path, make_pool([make_research_item()]))

    state = AtlasPipelineRunner(
        storage=storage,
        implementation_executor=executor,
        nexus_research_adapter=adapter,
    ).run_dry_run(AtlasPipelineRunRequest(pool_id="pool_1"))
    item = storage.load_pool("pool_1").get_item("research_1")

    assert adapter.request_calls == ["research_1"]
    assert adapter.run_calls == ["research_1"]
    assert executor.calls == []
    assert item is not None
    assert item.status == "completed"
    assert item.linked_context_pack_id
    assert item.metadata["context_pack_id"] == item.linked_context_pack_id
    assert state.status == "completed"
    assert state.item_results[0].context_pack_id == item.linked_context_pack_id
    assert state.item_results[0].context_pack_result["summary"] == "ok"
    assert any(event.event_type == "item_research_started" for event in state.events)
    assert any(event.event_type == "item_research_completed" for event in state.events)


def test_research_item_without_adapter_completes_with_warning_context_pack(tmp_path: Path) -> None:
    storage = make_storage(tmp_path, make_pool([make_research_item()]))

    state = AtlasPipelineRunner(storage=storage, nexus_research_adapter=None).run_dry_run(
        AtlasPipelineRunRequest(pool_id="pool_1")
    )
    item = storage.load_pool("pool_1").get_item("research_1")
    result = state.item_results[0]

    assert state.status == "completed"
    assert item is not None and item.status == "completed"
    assert result.context_pack_result["status"] == "completed_with_warnings"
    assert result.context_pack_result["insufficient_context"] is True
    assert result.context_pack_result["warnings"]
    assert "nexus_client_unavailable" in result.context_pack_result["warnings"]
    assert result.context_pack_id == item.linked_context_pack_id


def test_research_item_does_not_call_implementation_executor(tmp_path: Path) -> None:
    executor = FakeExecutor()
    storage = make_storage(tmp_path, make_pool([make_research_item()]))

    state = AtlasPipelineRunner(storage=storage, implementation_executor=executor).run_dry_run(
        AtlasPipelineRunRequest(pool_id="pool_1")
    )

    assert state.status == "completed"
    assert executor.calls == []


def test_research_item_policy_requires_approval_does_not_call_adapter(tmp_path: Path) -> None:
    adapter = FakeNexusAdapter()
    storage = make_storage(tmp_path, make_pool([make_research_item(risk_level="high")]))

    state = AtlasPipelineRunner(
        storage=storage,
        policy_gate=PoolAllowItemApprovalPolicyGate(),
        nexus_research_adapter=adapter,
    ).run_dry_run(AtlasPipelineRunRequest(pool_id="pool_1"))
    item = storage.load_pool("pool_1").get_item("research_1")

    assert state.status == "paused"
    assert adapter.request_calls == []
    assert adapter.run_calls == []
    assert item is not None and item.status == "approval_required"


def test_research_item_policy_block_does_not_call_adapter(tmp_path: Path) -> None:
    adapter = FakeNexusAdapter()
    storage = make_storage(tmp_path, make_pool([make_research_item(metadata={"action_type": "delete"})]))

    state = AtlasPipelineRunner(
        storage=storage,
        policy_gate=PoolAllowItemBlockPolicyGate(),
        nexus_research_adapter=adapter,
    ).run_dry_run(AtlasPipelineRunRequest(pool_id="pool_1"))
    item = storage.load_pool("pool_1").get_item("research_1")

    assert state.status == "blocked"
    assert adapter.request_calls == []
    assert adapter.run_calls == []
    assert item is not None and item.status == "blocked"


def test_research_item_adapter_exception_marks_item_failed(tmp_path: Path) -> None:
    adapter = FakeNexusAdapter(fail=True)
    storage = make_storage(tmp_path, make_pool([make_research_item()]))

    state = AtlasPipelineRunner(storage=storage, nexus_research_adapter=adapter).run_dry_run(
        AtlasPipelineRunRequest(pool_id="pool_1")
    )
    item = storage.load_pool("pool_1").get_item("research_1")

    assert item is not None and item.status == "failed"
    assert state.status == "failed"
    assert state.item_results[0].status == "failed"
    assert any("unexpected adapter boom" in error for error in state.item_results[0].errors)


def test_research_item_saves_context_pack_with_journal(tmp_path: Path) -> None:
    journal = AtlasJournal(tmp_path, workspace_id="ws_1")
    adapter = AtlasNexusResearchAdapter(nexus_client=FakeNexusClient(), journal=journal)
    storage = make_storage(tmp_path, make_pool([make_research_item()]))

    state = AtlasPipelineRunner(storage=storage, nexus_research_adapter=adapter).run_dry_run(
        AtlasPipelineRunRequest(pool_id="pool_1")
    )
    context_pack_id = state.item_results[0].context_pack_id
    json_path = tmp_path / "atlas" / "workspaces" / "ws_1" / "plan_pools" / "pool_1" / "context_packs" / f"{context_pack_id}.json"
    markdown_path = json_path.with_suffix(".md")

    assert state.status == "completed"
    assert context_pack_id
    assert json_path.exists()
    assert markdown_path.exists()


def test_runner_has_no_web_deep_research_or_runtime_side_effect_tokens() -> None:
    text = RUNNER_PATH.read_text(encoding="utf-8")

    for token in (
        "requests.",
        "httpx",
        "DeepResearch",
        "deep_research_job",
        "subprocess",
        "safe_apply(",
        "run_command(",
        ".unlink(",
    ):
        assert token not in text
