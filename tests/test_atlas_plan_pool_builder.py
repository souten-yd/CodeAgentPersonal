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
            {"step_id": "step_a", "title": "Edit A", "description": "Update A", "action_type": "update"},
            {"step_id": "step_b", "title": "Edit B", "description": "Update B", "action_type": "update"},
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
                "goal": "Preserve planner goal",
                "acceptance_criteria": ["Acceptance is preserved"],
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
    assert item.goal == "Preserve planner goal"
    assert item.description == "Map fields"
    assert item.target_files == ["agent/x.py"]
    assert item.risk_level == "critical"
    assert item.done_definition == ["Acceptance is preserved"]
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


def test_inspect_action_with_target_files_is_blocked_for_patch_generation() -> None:
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
    assert item.status == "blocked"
    assert item.metadata["action_type"] == ""


def test_high_risk_requires_confirmation_and_disables_auto_execution() -> None:
    payload = {"implementation_steps": [{"title": "Risky", "risk_level": "high"}]}

    item = AtlasPlanPoolBuilder().build_from_plan_payload(payload, root_goal="Goal", pool_id="pool_test").items[0]

    assert item.requires_user_confirmation is True
    assert item.auto_execution_allowed is False


def test_low_risk_can_be_auto_execution_allowed_but_not_executed() -> None:
    payload = {
        "destructive_change_detected": False,
        "implementation_steps": [{"title": "Safe", "risk_level": "low", "action_type": "update"}],
    }

    item = AtlasPlanPoolBuilder().build_from_plan_payload(payload, root_goal="Goal", pool_id="pool_test").items[0]

    assert item.requires_user_confirmation is False
    assert item.auto_execution_allowed is True


def test_fallback_pool_blocks_without_executable_items() -> None:
    pool = AtlasPlanPoolBuilder().build_from_plan_payload({}, root_goal="Goal", pool_id="pool_test")

    assert pool.status == "needs_revision"
    assert pool.items == []
    assert "planner_failure_requires_replan" in pool.warnings
    assert pool.metadata["patch_generation_allowed"] is False


def test_unknown_action_type_blocks_instead_of_normalizing_to_create() -> None:
    pool = AtlasPlanPoolBuilder().build_from_plan_payload(
        {"implementation_steps": [{"title": "Mystery", "action_type": "surprise", "target_files": ["new.py"]}]},
        root_goal="Goal",
        pool_id="pool_test",
    )

    item = pool.items[0]
    assert item.status == "blocked"
    assert item.metadata["action_type"] == ""
    assert "invalid_action_type:item_001" in pool.warnings


def test_explicit_and_compatible_legacy_actions_still_normalize() -> None:
    pool = AtlasPlanPoolBuilder().build_from_plan_payload(
        {
            "implementation_steps": [
                {"step_id": "create_step", "title": "Create", "action_type": "create", "target_files": ["new.py"]},
                {"step_id": "update_step", "title": "Update", "action_type": "update", "target_files": ["old.py"]},
                {"step_id": "patch_step", "title": "Patch", "action_type": "patch", "target_files": ["old.py"]},
                {"step_id": "write_step", "title": "Write", "action_type": "write", "target_files": ["newer.py"]},
            ]
        },
        root_goal="Goal",
        pool_id="pool_test",
    )

    assert [item.metadata["action_type"] for item in pool.items] == ["create", "update", "update", "create"]


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


def test_builder_preserves_codegen_contract_and_maps_requirements():
    pool = AtlasPlanPoolBuilder().build_from_plan_payload(
        {
            "root_goal": "Build score widget",
            "original_user_request": "Create a score widget and preserve reset.",
            "selected_architecture": "Use existing UI module",
            "constraints": ["No direct merge"],
            "preserve_behaviors": ["Reset button remains wired"],
            "requirements": [
                {"requirement_id": "req_score", "description": "Score increments"},
                {"requirement_id": "req_reset", "description": "Reset remains available"},
            ],
            "implementation_steps": [
                {
                    "step_id": "step_score",
                    "title": "Update score UI",
                    "description": "Implement score increment rendering with the existing UI module.",
                    "goal": "Score increments on click",
                    "action_type": "update",
                    "risk_level": "low",
                    "target_files": ["web/score.js"],
                    "requirement_ids": ["req_score", "req_reset"],
                    "acceptance_criteria": ["Score increments", "Reset still works"],
                    "expected_changes": ["Wire increment handler"],
                    "verification_contract": {"contract_id": "browser_dom", "signals": ["score", "reset"]},
                    "preserve_behaviors": ["Reset button remains wired"],
                }
            ],
        },
        pool_id="pool_test",
        automation_level="full_autopilot",
    )

    item = pool.items[0]
    assert pool.original_user_request == "Create a score widget and preserve reset."
    assert pool.selected_architecture == "Use existing UI module"
    assert pool.global_constraints == ["No direct merge"]
    assert pool.preserve_behaviors == ["Reset button remains wired"]
    assert pool.requirement_item_map == {"req_score": ["step_score"], "req_reset": ["step_score"]}
    assert pool.plan_quality["ok"] is True
    assert item.requirement_ids == ["req_score", "req_reset"]
    assert item.acceptance_criteria == ["Score increments", "Reset still works"]
    assert item.verification_contract["contract_id"] == "browser_dom"
    assert item.preserve_behaviors == ["Reset button remains wired"]


def test_builder_repairs_unmapped_requirement_for_single_applicable_item():
    pool = AtlasPlanPoolBuilder().build_from_plan_payload(
        {
            "requirements": [
                {"requirement_id": "req_mapped", "description": "Mapped requirement"},
                {"requirement_id": "req_missing", "description": "Missing requirement"},
            ],
            "implementation_steps": [
                {
                    "step_id": "step_1",
                    "title": "Mapped step",
                    "description": "Implement the mapped requirement completely.",
                    "action_type": "update",
                    "target_files": ["src/app.py"],
                    "requirement_ids": ["req_mapped"],
                    "acceptance_criteria": ["Mapped requirement works"],
                    "verification_contract": {"contract_id": "pytest"},
                }
            ],
        },
        root_goal="Goal",
        pool_id="pool_test",
        automation_level="full_autopilot",
    )

    item = pool.items[0]
    assert item.requirement_ids == ["req_mapped", "req_missing"]
    assert item.metadata["requirement_ids"] == ["req_mapped", "req_missing"]
    assert pool.requirement_item_map["req_missing"] == ["step_1"]
    assert pool.plan_quality["ok"] is True
    assert pool.metadata["requirement_mapping_diagnostics"][0]["type"] == "deterministic_single_item_requirement_assignment"


def test_builder_content_based_mapping_links_requirements_across_multi_step_plan():
    # The planner left requirements unlinked across a multi-step plan. The builder now links each one
    # to the step that most plausibly implements it (token overlap), so the plan is NOT blocked.
    pool = AtlasPlanPoolBuilder().build_from_plan_payload(
        {
            "requirements": [
                {"requirement_id": "req_move", "description": "Player ship moves left and right with arrow keys"},
                {"requirement_id": "req_enemy", "description": "Enemies spawn from the top and descend"},
            ],
            "implementation_steps": [
                {
                    "step_id": "step_move", "title": "Implement player movement",
                    "description": "Handle the player ship moving left and right via arrow keys.",
                    "action_type": "create", "target_files": ["script.js"], "requirement_ids": [],
                    "acceptance_criteria": ["Player ship moves left and right"], "verification_contract": {"contract_id": "pytest"},
                },
                {
                    "step_id": "step_enemy", "title": "Implement enemy spawning",
                    "description": "Spawn enemies from the top of the screen and make them descend.",
                    "action_type": "update", "target_files": ["script.js"], "requirement_ids": [],
                    "acceptance_criteria": ["Enemies spawn from the top"], "verification_contract": {"contract_id": "pytest"},
                },
            ],
        },
        root_goal="Goal",
        pool_id="pool_test",
        automation_level="plan_then_ask",
    )

    # Both requirements were linked to the right step, so nothing is blocked — even in supervised mode.
    assert "plan_revision_required" not in pool.metadata
    assert pool.requirement_item_map["req_move"] == ["step_move"]
    assert pool.requirement_item_map["req_enemy"] == ["step_enemy"]
    assert pool.plan_quality["ok"] is True
    diag_types = {d["type"] for d in pool.metadata.get("requirement_mapping_diagnostics", [])}
    assert "content_based_requirement_assignment" in diag_types


def _orphan_requirement_payload():
    # Second requirement shares no meaningful token with any step -> genuinely unmappable.
    return {
        "requirements": [
            {"requirement_id": "req_mapped", "description": "Mapped requirement"},
            {"requirement_id": "req_orphan", "description": "Telemetry beacon calibration"},
        ],
        "implementation_steps": [
            {
                "step_id": "step_1", "title": "Mapped step", "description": "Implement the mapped requirement completely.",
                "action_type": "update", "target_files": ["src/app.py"], "requirement_ids": ["req_mapped"],
                "acceptance_criteria": ["Mapped requirement works"], "verification_contract": {"contract_id": "pytest"},
            },
            {
                "step_id": "step_2", "title": "Other step", "description": "Render another part of the screen.",
                "action_type": "update", "target_files": ["src/other.py"], "requirement_ids": [],
                "acceptance_criteria": ["Other part works"], "verification_contract": {"contract_id": "pytest"},
            },
        ],
    }


def test_builder_truly_unmappable_requirement_requests_plan_revision_supervised():
    pool = AtlasPlanPoolBuilder().build_from_plan_payload(
        _orphan_requirement_payload(), root_goal="Goal", pool_id="pool_test", automation_level="plan_then_ask",
    )

    assert pool.metadata["plan_revision_required"] is True
    assert pool.metadata["patch_generation_recovery_decision"]["type"] == "request_plan_revision"
    assert pool.metadata["patch_generation_recovery_decision"]["unmapped_requirement_ids"] == ["req_orphan"]
    assert pool.plan_quality["ok"] is False
    assert "request_plan_revision:ambiguous_requirement_item_mapping" in pool.plan_quality["reasons"]


def test_builder_full_auto_does_not_block_on_truly_unmappable_requirement():
    # Even a genuinely unmappable requirement must not hard-block patch generation under full-auto.
    pool = AtlasPlanPoolBuilder().build_from_plan_payload(
        _orphan_requirement_payload(), root_goal="Goal", pool_id="pool_test", automation_level="full_autopilot",
    )

    assert "plan_revision_required" not in pool.metadata
    assert "patch_generation_recovery_decision" not in pool.metadata
    assert pool.metadata["requirement_mapping_ambiguous_full_auto_continued"]["type"] == "request_plan_revision"
    assert "full_auto_continued_with_ambiguous_requirement_mapping" in pool.warnings
