from pathlib import Path

import pytest

from app.atlas.conversational_shell_contract import (
    REQUIRED_VISIBLE_REGIONS,
    STATE_IDLE,
    WORK_TARGET_PLATFORM_SELF_IMPROVEMENT,
    WORK_TARGET_SOFTWARE_DEVELOPMENT_REPAIR,
    create_conversational_shell_contract,
    load_conversational_shell_contract,
    validate_conversational_shell_contract,
    write_conversational_shell_contract,
)


def test_create_conversational_shell_contract_ready_without_build_or_execution() -> None:
    contract = create_conversational_shell_contract(
        goal="Improve the Atlas conversation shell",
        work_target_mode=WORK_TARGET_SOFTWARE_DEVELOPMENT_REPAIR,
        conversation_state=STATE_IDLE,
    )

    assert contract["status"] == "ready"
    assert contract["buildless_shell_contract_enabled"] is True
    assert contract["backend_authoritative"] is True
    assert contract["workflow_state_source"] == "backend_workflow_state"
    assert contract["default_root_ui"] == "ui.html"
    assert contract["primary_cta_count"] == 1
    assert set(contract["required_visible_regions"]) == REQUIRED_VISIBLE_REGIONS
    assert contract["requires_npm_build"] is False
    assert contract["requires_vite"] is False
    assert contract["requires_vue_runtime"] is False
    assert contract["atlas_next_preview_optional"] is True
    assert contract["command_execution_enabled"] is False
    assert contract["execution_authority_enabled"] is False
    assert contract["autonomous_execution_enabled"] is False
    assert contract["patch_apply_enabled"] is False
    assert contract["candidate_apply_enabled"] is False
    assert contract["candidate_promotion_enabled"] is False
    assert contract["stable_runtime_mutation_enabled"] is False
    assert contract["direct_merge_enabled"] is False
    assert contract["remote_git_push_enabled"] is False
    assert contract["self_apply_enabled"] is False
    assert contract["self_modification_enabled"] is False
    assert contract["vue_authoritative"] is False
    assert contract["vue_approval_authority_enabled"] is False
    assert contract["vue_execution_controls_enabled"] is False
    assert contract["default_ui_promotion_enabled"] is False


def test_platform_self_improvement_mode_is_intent_only_without_authority() -> None:
    contract = create_conversational_shell_contract(
        goal="Improve Atlas itself",
        work_target_mode=WORK_TARGET_PLATFORM_SELF_IMPROVEMENT,
    )

    assert contract["status"] == "ready"
    assert contract["work_target_mode"] == WORK_TARGET_PLATFORM_SELF_IMPROVEMENT
    assert contract["platform_self_improvement_mode_available"] is True
    assert contract["work_target_mode_authorizes_self_improvement"] is False
    assert contract["self_improvement_requires_backend_gates"] is True
    assert contract["self_apply_enabled"] is False
    assert contract["self_modification_enabled"] is False
    assert contract["direct_merge_enabled"] is False


def test_contract_blocks_missing_goal_and_invalid_mode_or_state() -> None:
    contract = create_conversational_shell_contract(
        goal="",
        work_target_mode="execute_everything",
        conversation_state="unknown_state",
        selected_safety_profile="",
    )

    assert contract["status"] == "blocked"
    assert contract["buildless_shell_contract_enabled"] is False
    assert "goal_required" in contract["blocking_reasons"]
    assert "work_target_mode_not_allowed" in contract["blocking_reasons"]
    assert "conversation_state_not_allowed" in contract["blocking_reasons"]
    assert "selected_safety_profile_required" in contract["blocking_reasons"]


def test_validate_rejects_vue_authority_and_execution_authority() -> None:
    contract = create_conversational_shell_contract(
        goal="Keep Atlas shell display-only",
        work_target_mode=WORK_TARGET_SOFTWARE_DEVELOPMENT_REPAIR,
    )
    contract["vue_authoritative"] = True
    contract["command_execution_enabled"] = True

    with pytest.raises(ValueError, match="command_execution_enabled"):
        validate_conversational_shell_contract(contract)


def test_validate_rejects_missing_required_visible_region() -> None:
    contract = create_conversational_shell_contract(
        goal="Review shell regions",
        work_target_mode=WORK_TARGET_SOFTWARE_DEVELOPMENT_REPAIR,
    )
    contract["required_visible_regions"] = ["conversation_transcript"]

    with pytest.raises(ValueError, match="required_visible_regions"):
        validate_conversational_shell_contract(contract)


def test_write_and_load_conversational_shell_contract(tmp_path: Path) -> None:
    contract = create_conversational_shell_contract(
        goal="Persist shell contract",
        work_target_mode=WORK_TARGET_SOFTWARE_DEVELOPMENT_REPAIR,
    )

    path = write_conversational_shell_contract(
        contract=contract,
        destination=tmp_path / "conversational_shell.json",
    )
    loaded = load_conversational_shell_contract(manifest_path=path)

    assert loaded["contract_id"] == contract["contract_id"]
    assert loaded["goal"] == "Persist shell contract"


def test_conversational_shell_source_has_no_runtime_or_process_execution_dependency() -> None:
    text = Path("app/atlas/conversational_shell_contract.py").read_text(encoding="utf-8")
    forbidden = [
        "subprocess",
        "os.system",
        "requests",
        "from fastapi",
        "import fastapi",
        "uvicorn",
        "import main",
        "from main",
        "safe_apply",
        "git worktree",
    ]
    for needle in forbidden:
        assert needle not in text
