from pathlib import Path

import pytest

from app.atlas.conversational_shell_contract import (
    REQUIRED_VISIBLE_REGIONS,
    STATE_IDLE,
    WORK_TARGET_PLATFORM_SELF_IMPROVEMENT,
    WORK_TARGET_SOFTWARE_DEVELOPMENT_REPAIR,
    create_conversational_shell_contract,
)
from app.atlas.conversational_shell_model import (
    create_conversational_shell_model,
    validate_conversational_shell_model,
)


def _contract(mode: str = WORK_TARGET_SOFTWARE_DEVELOPMENT_REPAIR) -> dict:
    return create_conversational_shell_contract(
        goal="Build a usable Atlas shell",
        work_target_mode=mode,
        conversation_state=STATE_IDLE,
    )


def test_create_buildless_shell_model_from_contract() -> None:
    model = create_conversational_shell_model(
        contract=_contract(),
        conversation_messages=[{"role": "user", "content": "Start Atlas"}],
        changed_files=["app/atlas/conversational_shell_model.py"],
        verification_summary={"status": "planned", "summary": "focused contract tests"},
        recovery_summary={"status": "not_required"},
    )

    assert model["status"] == "ready"
    assert model["track_pr"] == "PR-ATLAS-SCALE-152"
    assert model["next_required_pr"] == "PR-ATLAS-SCALE-153"
    assert model["source_contract_track_pr"] == "PR-ATLAS-SCALE-151"
    assert model["backend_authoritative"] is True
    assert model["workflow_state_source"] == "backend_workflow_state"
    assert model["default_root_ui"] == "ui.html"
    assert model["buildless_shell_model_enabled"] is True
    assert set(model["required_visible_regions"]) == REQUIRED_VISIBLE_REGIONS
    for region in REQUIRED_VISIBLE_REGIONS:
        assert model[region]["region_id"] == region
    assert model["primary_cta"] == {
        "region_id": "primary_cta",
        "label": "Start Atlas",
        "enabled": True,
        "intent_only": True,
    }
    assert model["requires_npm_build"] is False
    assert model["requires_vite"] is False
    assert model["requires_vue_runtime"] is False
    assert model["command_execution_enabled"] is False
    assert model["execution_authority_enabled"] is False
    assert model["autonomous_execution_enabled"] is False
    assert model["patch_apply_enabled"] is False
    assert model["candidate_apply_enabled"] is False
    assert model["candidate_promotion_enabled"] is False
    assert model["stable_runtime_mutation_enabled"] is False
    assert model["direct_merge_enabled"] is False
    assert model["remote_git_push_enabled"] is False
    assert model["self_apply_enabled"] is False
    assert model["self_modification_enabled"] is False
    assert model["vue_authoritative"] is False
    assert model["default_ui_promotion_enabled"] is False


def test_work_target_mode_selector_is_backend_owned_and_intent_only() -> None:
    model = create_conversational_shell_model(
        contract=_contract(WORK_TARGET_PLATFORM_SELF_IMPROVEMENT),
    )
    selector = model["work_target_mode_selector"]

    assert selector["backend_owned"] is True
    assert selector["selected"] == WORK_TARGET_PLATFORM_SELF_IMPROVEMENT
    assert selector["authorizes_self_improvement"] is False
    assert {option["value"] for option in selector["options"]} == {
        WORK_TARGET_SOFTWARE_DEVELOPMENT_REPAIR,
        WORK_TARGET_PLATFORM_SELF_IMPROVEMENT,
    }
    assert sum(1 for option in selector["options"] if option["selected"]) == 1
    self_improvement = next(
        option for option in selector["options"] if option["value"] == WORK_TARGET_PLATFORM_SELF_IMPROVEMENT
    )
    assert self_improvement["requires_backend_gates"] is True
    assert self_improvement["authorizes_execution"] is False
    assert self_improvement["authorizes_self_improvement"] is False
    assert model["work_target_mode_authorizes_self_improvement"] is False


def test_blocked_contract_produces_disabled_shell_model() -> None:
    blocked_contract = create_conversational_shell_contract(goal="", work_target_mode="unknown")
    model = create_conversational_shell_model(contract=blocked_contract)

    assert model["status"] == "blocked"
    assert model["buildless_shell_model_enabled"] is False
    assert model["primary_cta"]["enabled"] is False
    assert "goal_required" in model["blocking_reasons"]
    assert "work_target_mode_not_allowed" in model["blocking_reasons"]


def test_validate_rejects_missing_region_or_authority_escalation() -> None:
    model = create_conversational_shell_model(contract=_contract())
    del model["verification_summary"]
    model["vue_authoritative"] = True

    with pytest.raises(ValueError, match="missing_required_fields:verification_summary"):
        validate_conversational_shell_model(model)


def test_changed_files_must_be_repo_relative() -> None:
    with pytest.raises(ValueError, match="changed_file_must_be_repo_relative"):
        create_conversational_shell_model(contract=_contract(), changed_files=["C:/outside/file.py"])


def test_shell_model_source_has_no_runtime_or_process_execution_dependency() -> None:
    text = Path("app/atlas/conversational_shell_model.py").read_text(encoding="utf-8")
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
        "git push",
        "npm",
        "vite",
    ]
    for needle in forbidden:
        assert needle not in text
