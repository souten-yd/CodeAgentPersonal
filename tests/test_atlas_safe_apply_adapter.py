from pathlib import Path

from agent.atlas_approval_gate import AtlasApprovalGate
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_safe_apply_adapter import AtlasSafeApplyAdapter
from agent.atlas_safe_apply_adapter_schema import AtlasSafeApplyRequest


ROOT = Path(__file__).resolve().parents[1]
ADAPTER_PATH = ROOT / "agent" / "atlas_safe_apply_adapter.py"


def make_item(
    *,
    item_id: str = "item_1",
    risk_level: str = "low",
    item_type: str = "implementation",
    status: str = "ready",
    target_files: list[str] | None = None,
    metadata: dict | None = None,
    requires_user_confirmation: bool = False,
) -> AtlasPlanItem:
    return AtlasPlanItem(
        item_id=item_id,
        pool_id="pool_1",
        title="Item 1",
        goal="Do item 1",
        item_type=item_type,
        status=status,
        risk_level=risk_level,
        target_files=target_files or ["agent/example.py"],
        metadata=metadata or {"action_type": "update"},
        requires_user_confirmation=requires_user_confirmation,
    )


def make_pool(item: AtlasPlanItem) -> AtlasPlanPool:
    return AtlasPlanPool(pool_id="pool_1", root_goal="Goal", status="ready", items=[item])


def approved_gate(item: AtlasPlanItem) -> AtlasApprovalGate:
    gate = AtlasApprovalGate()
    record = gate.request_approval(scope="item", pool_id=item.pool_id, item_id=item.item_id)
    gate.approve(record.approval_id)
    return gate


def test_low_risk_update_allowed_without_approval_when_no_confirmation_needed() -> None:
    item = make_item(metadata={"action_type": "update"})
    result = AtlasSafeApplyAdapter().evaluate_safe_apply(item, make_pool(item))

    assert result.decision == "allow"
    assert "low_risk" in result.categories
    assert "update_allowed" in result.categories


def test_non_low_risk_blocked() -> None:
    item = make_item(risk_level="high")
    result = AtlasSafeApplyAdapter().evaluate_safe_apply(item, make_pool(item))

    assert result.decision == "block"
    assert result.status == "blocked"
    assert "non_low_risk" in result.categories


def test_delete_action_blocked_even_with_approval() -> None:
    item = make_item(metadata={"action_type": "delete"})
    result = AtlasSafeApplyAdapter(approval_gate=approved_gate(item)).evaluate_safe_apply(item, make_pool(item))

    assert result.decision == "block"
    assert "delete_forbidden" in result.categories


def test_run_command_action_blocked_even_with_approval() -> None:
    item = make_item(metadata={"action_type": "run_command"})
    result = AtlasSafeApplyAdapter(approval_gate=approved_gate(item)).evaluate_safe_apply(item, make_pool(item))

    assert result.decision == "block"
    assert "run_command_forbidden" in result.categories


def test_protected_path_requires_approval() -> None:
    item = make_item(target_files=["ca_data/x.json"])
    result = AtlasSafeApplyAdapter().evaluate_safe_apply(item, make_pool(item))

    assert result.decision == "require_approval"
    assert "protected_path" in result.categories


def test_missing_required_approval_returns_require_approval() -> None:
    item = make_item(requires_user_confirmation=True)
    result = AtlasSafeApplyAdapter(approval_gate=AtlasApprovalGate()).evaluate_safe_apply(item, make_pool(item))

    assert result.decision == "require_approval"
    assert "approval_missing" in result.categories


def test_existing_item_approval_allows_low_risk_update() -> None:
    item = make_item(requires_user_confirmation=True)
    result = AtlasSafeApplyAdapter(approval_gate=approved_gate(item)).evaluate_safe_apply(item, make_pool(item))

    assert result.decision == "allow"
    assert "approval_present" in result.categories


def test_patch_metadata_block_blocks_safe_apply() -> None:
    item = make_item()
    result = AtlasSafeApplyAdapter().evaluate_safe_apply(item, make_pool(item), patch_metadata={"data_loss": True})

    assert result.decision == "block"
    assert "policy_blocked" in result.categories


def test_apply_low_risk_item_simulates_without_executor() -> None:
    item = make_item()
    request = AtlasSafeApplyRequest(pool_id="pool_1", item_id="item_1", allow_simulation_without_executor=True)
    result = AtlasSafeApplyAdapter().apply_low_risk_item(item, make_pool(item), request=request)

    assert result.status == "simulated"
    assert result.simulated is True
    assert result.applied is False


def test_apply_low_risk_item_fails_without_executor_when_simulation_disabled() -> None:
    item = make_item()
    request = AtlasSafeApplyRequest(pool_id="pool_1", item_id="item_1", allow_simulation_without_executor=False)
    result = AtlasSafeApplyAdapter().apply_low_risk_item(item, make_pool(item), request=request)

    assert result.status == "failed"
    assert "executor_missing" in result.categories


def test_apply_low_risk_item_calls_fake_executor_apply_plan_item_safe() -> None:
    class FakeExecutor:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def apply_plan_item_safe(self, item: AtlasPlanItem, pool: AtlasPlanPool) -> dict:
            self.calls.append({"item_id": item.item_id, "pool_id": pool.pool_id})
            return {"implementation_run_id": "impl_1"}

    item = make_item()
    executor = FakeExecutor()
    result = AtlasSafeApplyAdapter(implementation_executor=executor).apply_low_risk_item(item, make_pool(item))

    assert result.status == "applied"
    assert result.applied is True
    assert result.implementation_run_id == "impl_1"
    assert executor.calls == [{"item_id": "item_1", "pool_id": "pool_1"}]


def test_apply_low_risk_item_does_not_call_executor_when_requires_approval() -> None:
    class FakeExecutor:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def apply_plan_item_safe(self, item: AtlasPlanItem, pool: AtlasPlanPool) -> dict:
            self.calls.append(item.item_id)
            return {}

    item = make_item(requires_user_confirmation=True)
    executor = FakeExecutor()
    result = AtlasSafeApplyAdapter(approval_gate=AtlasApprovalGate(), implementation_executor=executor).apply_low_risk_item(
        item, make_pool(item)
    )

    assert result.status == "skipped"
    assert executor.calls == []


def test_adapter_has_no_direct_file_command_side_effect_tokens() -> None:
    text = ADAPTER_PATH.read_text(encoding="utf-8")

    for token in (
        "FastAPI",
        "@app.",
        "subprocess",
        ".write_text(",
        ".unlink(",
        "delete_file",
        "run_command(",
        "safe_apply(",
    ):
        assert token not in text
