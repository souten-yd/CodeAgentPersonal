from pathlib import Path

from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "agent" / "atlas_plan_pool_schema.py"


def test_plan_item_defaults() -> None:
    item = AtlasPlanItem(item_id="item_1", pool_id="pool_1", title="T", goal="G")

    assert item.status == "queued"
    assert item.item_type == "implementation"
    assert item.priority == "medium"
    assert item.risk_level == "medium"
    assert item.depends_on == []
    assert item.target_files == []
    assert item.retry_count == 0
    assert item.max_retries == 2
    assert item.created_at


def test_research_item_can_exist_without_target_files() -> None:
    item = AtlasPlanItem(
        item_id="item_1",
        pool_id="pool_1",
        title="Research",
        goal="Collect context",
        item_type="research",
    )

    assert item.target_files == []
    assert item.linked_context_pack_id == ""


def test_verification_item_can_hold_test_commands() -> None:
    item = AtlasPlanItem(
        item_id="item_1",
        pool_id="pool_1",
        title="Verify",
        goal="Verify changes",
        item_type="verification",
        test_commands=["pytest -q tests/test_x.py"],
    )

    assert item.model_dump()["test_commands"] == ["pytest -q tests/test_x.py"]


def test_plan_pool_defaults() -> None:
    pool = AtlasPlanPool(pool_id="pool_1", root_goal="Goal")

    assert pool.status == "draft"
    assert pool.planning_depth == "standard"
    assert pool.automation_level == "plan_then_ask"
    assert pool.execution_strategy == "sequential"
    assert pool.items == []


def test_plan_pool_holds_items_and_item_ids() -> None:
    item_1 = AtlasPlanItem(item_id="item_1", pool_id="pool_1", title="T1", goal="G1")
    item_2 = AtlasPlanItem(item_id="item_2", pool_id="pool_1", title="T2", goal="G2")
    pool = AtlasPlanPool(pool_id="pool_1", root_goal="Goal", items=[item_1, item_2])

    assert pool.item_ids() == ["item_1", "item_2"]
    assert pool.get_item("item_2") == item_2
    assert pool.get_item("missing") is None


def test_plan_pool_ready_items_respect_dependencies_and_status() -> None:
    item_1 = AtlasPlanItem(
        item_id="item_1",
        pool_id="pool_1",
        title="T1",
        goal="G1",
        status="ready",
    )
    item_2 = AtlasPlanItem(
        item_id="item_2",
        pool_id="pool_1",
        title="T2",
        goal="G2",
        status="ready",
        depends_on=["item_1"],
    )
    pool = AtlasPlanPool(pool_id="pool_1", root_goal="Goal", items=[item_1, item_2])

    assert pool.get_ready_items() == [item_1]

    pool.completed_item_ids = ["item_1"]
    item_1.status = "completed"

    assert pool.get_ready_items() == [item_2]


def test_schema_roundtrip_model_dump() -> None:
    item = AtlasPlanItem(item_id="item_1", pool_id="pool_1", title="T", goal="G")
    pool = AtlasPlanPool(pool_id="pool_1", root_goal="Goal", items=[item])

    payload = pool.model_dump()
    restored = AtlasPlanPool(**payload)

    assert restored.pool_id == "pool_1"
    assert restored.root_goal == "Goal"
    assert len(restored.items) == 1


def test_schema_roundtrip_preserves_codegen_contract_fields() -> None:
    item = AtlasPlanItem(
        item_id="item_1",
        pool_id="pool_1",
        title="T",
        goal="G",
        requirement_ids=["req_1"],
        acceptance_criteria=["Acceptance"],
        verification_contract={"contract_id": "pytest"},
        preserve_behaviors=["Keep behavior"],
        original_user_request="Original request",
        selected_architecture="Architecture",
    )
    pool = AtlasPlanPool(
        pool_id="pool_1",
        root_goal="Goal",
        original_user_request="Original request",
        selected_architecture="Architecture",
        global_constraints=["No push"],
        requirements=[{"requirement_id": "req_1", "description": "Requirement"}],
        preserve_behaviors=["Keep behavior"],
        requirement_item_map={"req_1": ["item_1"]},
        plan_quality={"ok": True, "reasons": []},
        items=[item],
    )

    restored = AtlasPlanPool(**pool.model_dump())

    assert restored.original_user_request == "Original request"
    assert restored.selected_architecture == "Architecture"
    assert restored.global_constraints == ["No push"]
    assert restored.requirements[0]["requirement_id"] == "req_1"
    assert restored.requirement_item_map == {"req_1": ["item_1"]}
    assert restored.items[0].requirement_ids == ["req_1"]
    assert restored.items[0].verification_contract["contract_id"] == "pytest"


def test_no_runtime_or_api_side_effect_tokens_in_schema() -> None:
    text = SCHEMA_PATH.read_text(encoding="utf-8")

    for token in (
        "FastAPI",
        "@app.",
        "subprocess",
        "ImplementationExecutor(",
        "safe_apply",
        "delete_file",
        "run_command",
    ):
        assert token not in text
