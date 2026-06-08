from __future__ import annotations

from agent.atlas_automation_profile_resolver import (
    is_full_auto_context,
    normalize_automation_profile,
)
from agent.atlas_critical_handling_policy import resolve_default_critical_handling


def test_all_supported_profile_preset_envelope_combinations_normalize() -> None:
    for preset in (
        "review_only",
        "single_action",
        "supervised_auto",
        "autonomous_custom",
        "autonomous_bounded_dev",
        "full_auto",
        "full_auto_multi_item_v1",
    ):
        resolved = normalize_automation_profile(preset_id=preset)
        assert resolved["preset_id"] == preset
        assert resolved["direct_merge_enabled"] is False
        assert resolved["remote_git_push_enabled"] is False
        assert resolved["self_apply_enabled"] is False
        assert resolved["stable_runtime_mutation_enabled"] is False
        assert resolved["vue_authority_enabled"] is False
        assert resolved["arbitrary_command_execution_enabled"] is False
        assert resolved["critical_user_approval_required"] is True


def test_unknown_values_fall_back_safely() -> None:
    resolved = normalize_automation_profile(
        profile="god_mode",
        preset_id="anything_goes",
        automation_level="unknown",
        envelope_id="wide_open",
        envelope_active=True,
    )

    assert resolved["profile"] == "review_only"
    assert resolved["preset_id"] == "review_only"
    assert resolved["automation_level"] == "manual_only"
    assert resolved["envelope_id"] == "none"
    assert resolved["autonomous_loop_active"] is False
    assert resolved["critical_handling_default"] == "block"
    assert resolved["blocking_reasons"]


def test_autonomous_profile_alone_is_capable_not_loop_active() -> None:
    resolved = normalize_automation_profile(profile="autonomous_dev_agent")

    assert resolved["runtime_level"] == "level_8_fully_autonomous_code_agent"
    assert resolved["full_auto_capable"] is True
    assert resolved["autonomous_loop_active"] is False
    assert resolved["critical_handling_default"] == "ask"


def test_bounded_dev_envelope_activates_bounded_loop() -> None:
    resolved = normalize_automation_profile(
        preset_id="autonomous_bounded_dev",
        envelope_id="pre_authorized_bounded_dev_envelope",
        envelope_active=True,
    )

    assert resolved["profile"] == "autonomous_dev_agent"
    assert resolved["automation_level"] == "full_autopilot"
    assert resolved["autonomous_loop_active"] is True
    assert resolved["max_actions"] == 12
    # Dev/repair allows the whole selected-project work root via the "." sentinel.
    assert resolved["allowed_paths"] == ["."]


def test_self_improvement_envelope_requires_strict_gate() -> None:
    blocked = normalize_automation_profile(
        profile="autonomous_dev_agent",
        envelope_id="pre_authorized_self_improvement_envelope",
        envelope_active=True,
    )
    assert blocked["self_improvement"] is True
    assert blocked["autonomous_loop_active"] is False
    assert "strict_gate_required_by_self_improvement_envelope" in blocked["blocking_reasons"]

    allowed = normalize_automation_profile(
        profile="autonomous_dev_agent",
        envelope_id="pre_authorized_self_improvement_envelope",
        envelope_active=True,
        strict_gate_approved=True,
    )
    assert allowed["autonomous_loop_active"] is True
    assert allowed["critical_handling_default"] == "ask"
    assert "main.py" in allowed["blocked_paths"]


def test_full_auto_context_and_critical_handling_use_resolver() -> None:
    assert is_full_auto_context(preset_id="full_auto") is True
    assert is_full_auto_context(preset_id="autonomous_bounded_dev") is True
    assert is_full_auto_context(preset_id="single_action") is False
    assert resolve_default_critical_handling(preset_id="autonomous_bounded_dev") == "auto"
    assert (
        resolve_default_critical_handling(
            profile="autonomous_dev_agent",
            envelope_id="pre_authorized_self_improvement_envelope",
            envelope_active=True,
            strict_gate_approved=True,
        )
        == "ask"
    )
