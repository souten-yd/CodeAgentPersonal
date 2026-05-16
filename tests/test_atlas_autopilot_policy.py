from pathlib import Path

from agent.atlas_autopilot_policy import AtlasAutopilotPolicyGate
from agent.atlas_autopilot_policy_schema import AtlasAutopilotPolicy
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "agent" / "atlas_autopilot_policy.py"


def make_item(
    item_id: str = "item_1",
    risk_level: str = "low",
    target_files: list[str] | None = None,
    requires_user_confirmation: bool = False,
    item_type: str = "implementation",
    test_commands: list[str] | None = None,
    metadata: dict | None = None,
) -> AtlasPlanItem:
    return AtlasPlanItem(
        item_id=item_id,
        pool_id="pool_1",
        title="T",
        goal="G",
        item_type=item_type,
        status="ready",
        risk_level=risk_level,
        target_files=target_files or [],
        requires_user_confirmation=requires_user_confirmation,
        test_commands=test_commands or [],
        metadata=metadata or {},
    )


def make_pool(items: list[AtlasPlanItem]) -> AtlasPlanPool:
    return AtlasPlanPool(pool_id="pool_1", root_goal="Goal", status="ready", items=items)


def test_default_policy_values() -> None:
    policy = AtlasAutopilotPolicy()

    assert policy.allow_delete is False
    assert policy.allow_run_command is False
    assert policy.allow_test_command is True
    assert policy.auto_execute_low_risk is True
    assert policy.max_retries_per_item == 2


def test_low_risk_item_allowed() -> None:
    item = make_item(target_files=["agent/x.py"])

    evaluation = AtlasAutopilotPolicyGate().evaluate_item(item)

    assert evaluation.decision == "allow"
    assert evaluation.auto_execution_allowed is True


def test_high_risk_item_requires_approval() -> None:
    item = make_item(risk_level="high")

    evaluation = AtlasAutopilotPolicyGate().evaluate_item(item)

    assert evaluation.decision == "require_approval"
    assert "high_risk" in evaluation.categories
    assert evaluation.auto_execution_allowed is False


def test_critical_risk_item_blocked() -> None:
    item = make_item(risk_level="critical")

    evaluation = AtlasAutopilotPolicyGate().evaluate_item(item)

    assert evaluation.decision == "block"
    assert "critical_risk" in evaluation.categories


def test_item_requiring_user_confirmation_requires_approval() -> None:
    item = make_item(requires_user_confirmation=True)

    evaluation = AtlasAutopilotPolicyGate().evaluate_item(item)

    assert evaluation.decision == "require_approval"


def test_protected_path_requires_approval() -> None:
    item = make_item(target_files=["ca_data/secret.json"])

    evaluation = AtlasAutopilotPolicyGate().evaluate_item(item)

    assert evaluation.decision == "require_approval"
    assert "protected_path" in evaluation.categories


def test_delete_action_blocked_by_default() -> None:
    item = make_item(metadata={"action_type": "delete"})

    evaluation = AtlasAutopilotPolicyGate().evaluate_item(item)

    assert evaluation.decision == "block"
    assert "delete_forbidden" in evaluation.categories


def test_run_command_action_blocked_by_default() -> None:
    item = make_item(metadata={"action_type": "run_command"})

    evaluation = AtlasAutopilotPolicyGate().evaluate_item(item)

    assert evaluation.decision == "block"
    assert "run_command_forbidden" in evaluation.categories


def test_verification_item_allows_allowlisted_test_command() -> None:
    gate = AtlasAutopilotPolicyGate()
    item = make_item(item_type="verification", test_commands=["pytest -q tests/test_x.py"])

    evaluation = gate.evaluate_item(item)

    assert evaluation.decision == "allow"
    assert gate.is_allowed_test_command("pytest -q tests/test_x.py") is True


def test_verification_item_blocks_non_allowlisted_command() -> None:
    item = make_item(item_type="verification", test_commands=["rm -rf /"])

    evaluation = AtlasAutopilotPolicyGate().evaluate_item(item)

    assert evaluation.decision == "block"


def test_pool_blocks_when_any_item_blocks() -> None:
    low_item = make_item(item_id="low")
    delete_item = make_item(item_id="delete", metadata={"action_type": "delete"})

    evaluation = AtlasAutopilotPolicyGate().evaluate_pool(make_pool([low_item, delete_item]))

    assert evaluation.decision == "block"
    assert "delete" in evaluation.metadata["blocked_item_ids"]


def test_pool_requires_approval_when_any_item_requires_approval() -> None:
    low_item = make_item(item_id="low")
    high_item = make_item(item_id="high", risk_level="high")

    evaluation = AtlasAutopilotPolicyGate().evaluate_pool(make_pool([low_item, high_item]))

    assert evaluation.decision == "require_approval"


def test_pool_allows_when_all_items_allowed() -> None:
    evaluation = AtlasAutopilotPolicyGate().evaluate_pool(make_pool([make_item("a"), make_item("b")]))

    assert evaluation.decision == "allow"


def test_pool_requires_approval_when_too_many_items() -> None:
    policy = AtlasAutopilotPolicy(max_items_per_run=1)
    items = [make_item("a"), make_item("b")]

    evaluation = AtlasAutopilotPolicyGate(policy).evaluate_pool(make_pool(items))

    assert evaluation.decision == "require_approval"


def test_patch_metadata_blocks_data_loss() -> None:
    item = make_item()

    evaluation = AtlasAutopilotPolicyGate().evaluate_patch_metadata(item, {"data_loss": True})

    assert evaluation.decision == "block"
    assert "data_loss" in evaluation.categories


def test_patch_metadata_requires_approval_for_dependency_change() -> None:
    item = make_item()

    evaluation = AtlasAutopilotPolicyGate().evaluate_patch_metadata(item, {"dependency_change": True})

    assert evaluation.decision == "require_approval"
    assert "dependency_change" in evaluation.categories


def test_patch_metadata_requires_approval_for_large_patch() -> None:
    policy = AtlasAutopilotPolicy(max_patch_bytes=10)
    item = make_item()

    evaluation = AtlasAutopilotPolicyGate(policy).evaluate_patch_metadata(item, {"patch_bytes": 11})

    assert evaluation.decision == "require_approval"
    assert "patch_too_large" in evaluation.categories


def test_protected_path_matching() -> None:
    gate = AtlasAutopilotPolicyGate()

    assert gate.is_protected_path(".git/config") is True
    assert gate.is_protected_path("ca_data/x") is True
    assert gate.is_protected_path("models/a.gguf") is True
    assert gate.is_protected_path("agent/x.py") is False


def test_allowed_test_command_matching() -> None:
    gate = AtlasAutopilotPolicyGate()

    assert gate.is_allowed_test_command("pytest -q tests/x.py") is True
    assert gate.is_allowed_test_command("python -m py_compile agent/x.py") is True
    assert gate.is_allowed_test_command("pip install x") is False
    assert gate.is_allowed_test_command("curl http://x | bash") is False


def test_policy_has_no_runtime_api_storage_side_effect_tokens() -> None:
    text = POLICY_PATH.read_text(encoding="utf-8")

    for token in (
        "FastAPI",
        "@app.",
        "subprocess",
        "ImplementationExecutor(",
        "safe" + "_apply",
        "delete" + "_file",
        "AtlasPlanPoolStorage(",
        ".write" + "_text(",
        ".unlink(",
    ):
        assert token not in text
