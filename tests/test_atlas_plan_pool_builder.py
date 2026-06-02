from pathlib import Path

from agent.atlas_plan_pool_builder import AtlasPlanPoolBuilder
from agent.atlas_plan_pool_schema import AtlasPlanPool


ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = ROOT / "agent" / "atlas_plan_pool_builder.py"


def test_build_from_plan_payload_creates_pool_and_items() -> None:
    payload = {
        "plan_id": "plan_1",
        "requirement_id": "req_1",
        "implementation_steps": [
            {"step_id": "step_a", "title": "Edit A", "description": "Update A"},
            {"step_id": "step_b", "title": "Edit B", "description": "Update B"},
        ],
    }

    pool = AtlasPlanPoolBuilder().build_from_plan_payload(payload, root_goal="Goal", pool_id="pool_test")

    assert isinstance(pool, AtlasPlanPool)
    assert pool.pool_id == "pool_test"
    assert pool.linked_plan_id == "plan_1"
    assert pool.linked_requirement_id == "req_1"
    assert len(pool.items) == 2
    assert pool.items[0].status == "ready"
    assert pool.items[1].status == "queued"
    assert pool.items[1].depends_on == ["step_a"]


def test_step_fields_are_mapped_to_plan_item() -> None:
    payload = {
        "plan_id": "plan_1",
        "requirement_id": "req_1",
        "rollback_plan": ["Restore previous version"],
        "implementation_steps": [
            {
                "title": "Update builder",
                "description": "Map fields",
                "target_files": ["agent/x.py"],
                "risk_level": "critical",
                "verification": ["Run focused tests"],
                "rollback": ["Revert builder change"],
                "expected_changes": ["Adds mapping"],
            }
        ],
    }

    item = AtlasPlanPoolBuilder().build_from_plan_payload(payload, root_goal="Goal", pool_id="pool_test").items[0]

    assert item.title == "Update builder"
    assert item.goal == "Map fields"
    assert item.description == "Map fields"
    assert item.target_files == ["agent/x.py"]
    assert item.risk_level == "critical"
    assert item.done_definition == ["Run focused tests"]
    assert item.rollback_plan == ["Revert builder change"]
    assert item.expected_changes == ["Adds mapping"]


def test_test_action_becomes_verification_item() -> None:
    payload = {
        "implementation_steps": [
            {
                "action_type": "test",
                "title": "Run tests",
                "command": "pytest -q tests/test_x.py",
            }
        ]
    }

    item = AtlasPlanPoolBuilder().build_from_plan_payload(payload, root_goal="Goal", pool_id="pool_test").items[0]

    assert item.item_type == "verification"
    assert item.test_commands == ["pytest -q tests/test_x.py"]


def test_inspect_action_becomes_research_item() -> None:
    payload = {"implementation_steps": [{"action_type": "inspect", "title": "Inspect code"}]}

    item = AtlasPlanPoolBuilder().build_from_plan_payload(payload, root_goal="Goal", pool_id="pool_test").items[0]

    assert item.item_type == "research"


def test_inspect_action_with_target_files_is_reclassified_as_implementation() -> None:
    payload = {
        "implementation_steps": [
            {
                "action_type": "inspect",
                "title": "Create index.html",
                "description": "Create an HTML file for the requested page.",
                "target_files": ["index.html"],
            }
        ]
    }

    item = AtlasPlanPoolBuilder().build_from_plan_payload(payload, root_goal="HTML を作って", pool_id="pool_test").items[0]

    assert item.item_type == "implementation"
    assert item.metadata["action_type"] == "create"


def test_high_risk_requires_confirmation_and_disables_auto_execution() -> None:
    payload = {"implementation_steps": [{"title": "Risky", "risk_level": "high"}]}

    item = AtlasPlanPoolBuilder().build_from_plan_payload(payload, root_goal="Goal", pool_id="pool_test").items[0]

    assert item.requires_user_confirmation is True
    assert item.auto_execution_allowed is False


def test_low_risk_can_be_auto_execution_allowed_but_not_executed() -> None:
    payload = {
        "destructive_change_detected": False,
        "implementation_steps": [{"title": "Safe", "risk_level": "low"}],
    }

    item = AtlasPlanPoolBuilder().build_from_plan_payload(payload, root_goal="Goal", pool_id="pool_test").items[0]

    assert item.requires_user_confirmation is False
    assert item.auto_execution_allowed is True


def test_fallback_pool_generates_research_planning_verification_items() -> None:
    pool = AtlasPlanPoolBuilder().build_from_plan_payload({}, root_goal="Goal", pool_id="pool_test")

    assert len(pool.items) == 3
    assert [item.item_type for item in pool.items] == ["research", "planning", "verification"]
    assert [item.status for item in pool.items] == ["ready", "queued", "queued"]
    assert pool.items[1].depends_on == ["item_001"]
    assert pool.items[2].depends_on == ["item_002"]
    assert "fallback_plan_items_generated" in pool.warnings


def test_build_from_autopilot_plan_dict_uses_tasks() -> None:
    autopilot_plan = {
        "autopilot_id": "auto_1",
        "user_goal": "Goal",
        "tasks": [
            {
                "task_id": "task_1",
                "title": "Research",
                "description": "Inspect context",
                "task_type": "research",
                "acceptance_criteria": ["Context summarized"],
            },
            {
                "task_id": "task_2",
                "title": "Implement",
                "depends_on": ["task_1"],
                "acceptance_criteria": ["Code updated"],
            },
        ],
    }

    pool = AtlasPlanPoolBuilder().build_from_autopilot_plan(autopilot_plan, pool_id="pool_test")

    assert pool.linked_autopilot_id == "auto_1"
    assert pool.items[0].item_id == "task_1"
    assert pool.items[0].title == "Research"
    assert pool.items[0].item_type == "research"
    assert pool.items[0].done_definition == ["Context summarized"]
    assert pool.items[1].depends_on == ["task_1"]
    assert pool.items[1].done_definition == ["Code updated"]


def test_build_from_autopilot_plan_respects_execution_order() -> None:
    autopilot_plan = {
        "user_goal": "Goal",
        "execution_order": ["task_2", "task_1"],
        "tasks": [
            {"task_id": "task_1", "title": "First in payload"},
            {"task_id": "task_2", "title": "First to execute"},
        ],
    }

    pool = AtlasPlanPoolBuilder().build_from_autopilot_plan(autopilot_plan, pool_id="pool_test")

    assert [item.item_id for item in pool.items] == ["task_2", "task_1"]


def test_builder_has_no_runtime_api_or_storage_side_effect_tokens() -> None:
    text = BUILDER_PATH.read_text(encoding="utf-8")

    for token in (
        "FastAPI",
        "@app.",
        "subprocess",
        "ImplementationExecutor(",
        "safe" + "_apply",
        "run" + "_command",
        "delete" + "_file",
        "AtlasPlanPoolStorage(",
    ):
        assert token not in text


def test_builder_does_not_write_files(monkeypatch) -> None:
    def fail_write_text(*args, **kwargs):
        raise AssertionError("builder should not write files")

    monkeypatch.setattr(Path, "write_text", fail_write_text)

    pool = AtlasPlanPoolBuilder().build_from_plan_payload(
        {"implementation_steps": [{"title": "No write"}]}, root_goal="Goal", pool_id="pool_test"
    )

    assert pool.pool_id == "pool_test"
    assert len(pool.items) == 1
def test_builder_carries_file_changes_and_normalizes_target_files():
    pool = AtlasPlanPoolBuilder().build_from_plan_payload(
        {
            "root_goal": "g",
            "implementation_steps": [
                {
                    "step_id": "step_1",
                    "title": "create web app",
                    "action_type": "create",
                    "risk_level": "low",
                    "target_files": ["index.html"],
                    "file_changes": [
                        {"path": "index.html", "action_type": "create", "proposed_content": "<!doctype html>\n"},
                        {"path": "style.css", "action_type": "create", "proposed_content": "body{}\n"},
                    ],
                }
            ],
        }
    )
    item = pool.items[0]
    assert item.metadata["file_changes"][1]["path"] == "style.css"
    assert item.target_files == ["index.html", "style.css"]
    assert item.metadata["change_set"]["apply_strategy"] == "preflight_all_then_apply_all"
