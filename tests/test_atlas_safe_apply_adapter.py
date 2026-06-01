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


# ── full_auto relaxation (single source of truth via atlas_full_auto_gate) ────


def test_full_auto_allows_high_risk_update_without_approval() -> None:
    item = make_item(risk_level="high")
    result = AtlasSafeApplyAdapter().evaluate_safe_apply(item, make_pool(item), preset_id="full_auto")

    assert result.decision == "allow"
    assert "full_auto_approval_bypassed" in result.categories


def test_full_auto_bypasses_patch_metadata_dependency_change() -> None:
    item = make_item(risk_level="high")
    result = AtlasSafeApplyAdapter().evaluate_safe_apply(
        item, make_pool(item), patch_metadata={"dependency_change": True}, preset_id="full_auto"
    )

    assert result.decision == "allow"


def test_full_auto_routes_patch_metadata_data_loss_to_critical_decision() -> None:
    item = make_item()
    result = AtlasSafeApplyAdapter().evaluate_safe_apply(
        item, make_pool(item), patch_metadata={"data_loss": True}, preset_id="full_auto"
    )

    assert result.decision == "require_approval"
    assert result.metadata["status"] == "waiting_for_critical_decision"
    assert result.metadata["critical_event"]["critical_event"] is True


def test_full_auto_bypasses_low_risk_requires_user_confirmation() -> None:
    # Previously leaked through the medium/high-only hardcode; full_auto must bypass at any risk.
    item = make_item(risk_level="low", requires_user_confirmation=True)
    result = AtlasSafeApplyAdapter().evaluate_safe_apply(item, make_pool(item), preset_id="full_auto")

    assert result.decision == "allow"


def test_autonomous_preset_ids_treated_as_full_auto() -> None:
    for preset in ("full_auto_multi_item_v1", "autonomous_bounded_dev", "autonomous_custom"):
        item = make_item(risk_level="high")
        result = AtlasSafeApplyAdapter().evaluate_safe_apply(item, make_pool(item), preset_id=preset)
        assert result.decision == "allow", preset


def test_full_auto_requires_critical_decision_on_critical_risk() -> None:
    item = make_item(risk_level="critical")
    result = AtlasSafeApplyAdapter().evaluate_safe_apply(item, make_pool(item), preset_id="full_auto")

    assert result.decision == "require_approval"
    assert "critical_risk_not_allowed" in result.reasons
    assert result.metadata["status"] == "waiting_for_critical_decision"


def test_full_auto_keeps_approval_on_protected_path() -> None:
    item = make_item(risk_level="high", target_files=["ca_data/x.json"])
    result = AtlasSafeApplyAdapter().evaluate_safe_apply(item, make_pool(item), preset_id="full_auto")

    assert result.decision == "require_approval"
    assert "protected_path" in result.categories


def test_guarded_low_risk_preset_still_blocks_high_risk() -> None:
    item = make_item(risk_level="high")
    result = AtlasSafeApplyAdapter().evaluate_safe_apply(item, make_pool(item), preset_id="guarded_low_risk")

    assert result.decision == "block"


def _pool_with_features(item: AtlasPlanItem, critical_handling: str) -> AtlasPlanPool:
    return AtlasPlanPool(
        pool_id="pool_1", root_goal="Goal", status="ready", items=[item],
        metadata={"automation_features": {"critical_handling": critical_handling}},
    )


def test_full_auto_security_patch_routed_by_critical_handling_ask() -> None:
    item = make_item(risk_level="high")
    result = AtlasSafeApplyAdapter().evaluate_safe_apply(
        item, _pool_with_features(item, "ask"), patch_metadata={"security": True}, preset_id="full_auto"
    )
    assert result.decision == "require_approval"


def test_full_auto_security_patch_ignores_critical_handling_block_and_waits() -> None:
    item = make_item(risk_level="high")
    result = AtlasSafeApplyAdapter().evaluate_safe_apply(
        item, _pool_with_features(item, "block"), patch_metadata={"security": True}, preset_id="full_auto"
    )
    assert result.decision == "require_approval"
    assert result.metadata["status"] == "waiting_for_critical_decision"


def test_full_auto_security_patch_ignores_critical_handling_auto_and_waits() -> None:
    item = make_item(risk_level="high")
    result = AtlasSafeApplyAdapter().evaluate_safe_apply(
        item, _pool_with_features(item, "auto"), patch_metadata={"security": True}, preset_id="full_auto"
    )
    assert result.decision == "require_approval"
    assert result.metadata["critical_event"]["critical_event"] is True


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


def _critical_event(category="critical_risk", files=None, capabilities=None):
    return {
        "critical_event": True,
        "category": category,
        "affected_files": files or ["agent/example.py"],
        "affected_capabilities": capabilities or ["safe_apply_gate"],
        "status": "waiting_for_critical_decision",
    }


def _approved_critical_metadata(event=None, files=None, capabilities=None, *, one_action_only=True):
    event = event or _critical_event(files=files, capabilities=capabilities)
    return {
        "action_type": "update",
        "critical_event": event,
        "approval": {
            "decision": "approved",
            "one_action_only": one_action_only,
            "bounded_continuation": False,
            "approved_files": files or event["affected_files"],
            "approved_capabilities": capabilities or event["affected_capabilities"],
            "critical_event": event,
        },
    }


def test_approved_critical_risk_item_can_proceed_with_exact_files_and_capabilities() -> None:
    event = _critical_event(files=["agent/example.py"], capabilities=["safe_apply_gate"])
    item = make_item(risk_level="critical", target_files=["agent/example.py"], metadata=_approved_critical_metadata(event))

    result = AtlasSafeApplyAdapter().evaluate_safe_apply(item, make_pool(item), preset_id="full_auto")

    assert result.decision == "allow"
    assert "critical_approval_present" in result.categories
    assert result.metadata["critical_approval"]["approved_files"] == ["agent/example.py"]


def test_approved_critical_risk_item_requires_approval_when_scope_does_not_match() -> None:
    event = _critical_event(files=["agent/example.py"], capabilities=["safe_apply_gate"])
    metadata = _approved_critical_metadata(event, files=["agent/other.py"], capabilities=["safe_apply_gate"])
    item = make_item(risk_level="critical", target_files=["agent/example.py"], metadata=metadata)

    result = AtlasSafeApplyAdapter().evaluate_safe_apply(item, make_pool(item), preset_id="full_auto")

    assert result.decision == "require_approval"
    assert result.metadata["status"] == "waiting_for_critical_decision"
    assert "critical_approval_missing_or_invalid" in result.categories


def test_approved_critical_risk_item_requires_approval_when_capability_does_not_match() -> None:
    event = _critical_event(files=["agent/example.py"], capabilities=["safe_apply_gate"])
    metadata = _approved_critical_metadata(event, files=["agent/example.py"], capabilities=["documentation_only"])
    item = make_item(risk_level="critical", target_files=["agent/example.py"], metadata=metadata)

    result = AtlasSafeApplyAdapter().evaluate_safe_apply(item, make_pool(item), preset_id="full_auto")

    assert result.decision == "require_approval"
    assert "critical_approval_missing_or_invalid" in result.categories


def test_hard_forbidden_categories_remain_blocked_with_ordinary_critical_approval() -> None:
    for category in (
        "delete_forbidden",
        "run_command_forbidden",
        "direct_merge",
        "remote_push",
        "self_apply",
        "stable_runtime_mutation",
        "unbounded_automation",
    ):
        event = _critical_event(category=category, capabilities=[category])
        metadata = _approved_critical_metadata(event, capabilities=[category])
        if category == "delete_forbidden":
            metadata["action_type"] = "delete"
        elif category == "run_command_forbidden":
            metadata["action_type"] = "run_command"
        else:
            metadata["forbidden_categories"] = [category]
        item = make_item(risk_level="critical", metadata=metadata)

        result = AtlasSafeApplyAdapter().evaluate_safe_apply(item, make_pool(item), preset_id="full_auto")

        assert result.decision == "block", category
        assert result.status == "blocked", category
        assert category in result.categories, category
