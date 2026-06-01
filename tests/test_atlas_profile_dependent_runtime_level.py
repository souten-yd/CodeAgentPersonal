"""Profile-dependent runtime model: runtime level is resolved per selected profile.

Defaults stay on the safe end; only ``autonomous_dev_agent`` reaches Level 8, and the
forbidden capability flags remain False at every level (Level 8 included).
"""

from __future__ import annotations

import pytest

from app.atlas.automation_safety_profile import (
    DEFAULT_RUNTIME_LEVEL,
    MAX_RUNTIME_LEVEL,
    PROFILE_AUTONOMOUS_DEV_AGENT,
    PROFILE_GUARDED_SINGLE_ACTION,
    PROFILE_REVIEW_ONLY,
    PROFILE_SUPERVISED_BOUNDED_AUTO,
    RUNTIME_LEVEL_BY_PROFILE,
    create_automation_safety_profile,
    resolve_runtime_level_for_profile,
    validate_automation_safety_profile,
)

_EXPECTED = {
    PROFILE_REVIEW_ONLY: "level_0_review_only",
    PROFILE_GUARDED_SINGLE_ACTION: "level_1_guarded_single_step",
    PROFILE_SUPERVISED_BOUNDED_AUTO: "level_2_to_level4_supervised_bounded_auto",
    PROFILE_AUTONOMOUS_DEV_AGENT: "level_8_fully_autonomous_code_agent",
}


@pytest.mark.parametrize("profile,expected", list(_EXPECTED.items()))
def test_resolve_runtime_level_for_profile(profile: str, expected: str) -> None:
    assert resolve_runtime_level_for_profile(profile) == expected
    assert RUNTIME_LEVEL_BY_PROFILE[profile] == expected


def test_unknown_profile_falls_back_to_safe_default() -> None:
    assert resolve_runtime_level_for_profile("not_a_profile") == DEFAULT_RUNTIME_LEVEL


@pytest.mark.parametrize("profile,expected", list(_EXPECTED.items()))
def test_create_profile_resolves_runtime_level(profile: str, expected: str) -> None:
    result = create_automation_safety_profile(profile=profile, explicit_profile_selection=True)
    assert result["runtime_level"] == expected
    assert result["runtime_level_model"] == "profile_dependent"
    assert result["default_runtime_level"] == DEFAULT_RUNTIME_LEVEL
    assert result["max_runtime_level"] == MAX_RUNTIME_LEVEL
    # validate() must accept the per-profile runtime level.
    validate_automation_safety_profile(result)


def test_default_profile_is_safe_not_level_8() -> None:
    result = create_automation_safety_profile(explicit_profile_selection=True)
    assert result["automation_safety_profile"] == PROFILE_REVIEW_ONLY
    assert result["runtime_level"] == "level_0_review_only"
    assert result["runtime_level"] != MAX_RUNTIME_LEVEL


def test_level_8_keeps_forbidden_flags_false() -> None:
    result = create_automation_safety_profile(
        profile=PROFILE_AUTONOMOUS_DEV_AGENT, explicit_profile_selection=True
    )
    assert result["runtime_level"] == "level_8_fully_autonomous_code_agent"
    for flag in (
        "direct_merge_enabled",
        "remote_git_push_enabled",
        "self_apply_enabled",
        "self_modification_enabled",
        "stable_runtime_mutation_enabled",
        "vue_authoritative",
        "vue_execution_controls_enabled",
    ):
        assert result[flag] is False, flag


def test_validate_rejects_wrong_runtime_level_for_profile() -> None:
    result = create_automation_safety_profile(
        profile=PROFILE_REVIEW_ONLY, explicit_profile_selection=True
    )
    result["runtime_level"] = "level_8_fully_autonomous_code_agent"
    with pytest.raises(ValueError):
        validate_automation_safety_profile(result)
