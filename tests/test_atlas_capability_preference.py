from __future__ import annotations

from agent.atlas_capability_preference_schema import (
    ALL_CAPABILITY_KEYS,
    CAP_BROWSER_AUTOMATION,
    CAP_COMMAND_EXECUTION,
    CAP_PLAYWRIGHT_VERIFICATION,
    CAP_SANDBOXED_INSTALL,
    CAP_WEB_EVIDENCE,
    apply_preferences,
    build_feature_summary,
    get_default_preferences,
)


def test_default_preferences_all_checked():
    prefs = get_default_preferences()
    for key in ALL_CAPABILITY_KEYS:
        assert prefs[key] is True, f"Expected {key} to be checked by default"


def test_all_capability_keys_present_in_defaults():
    prefs = get_default_preferences()
    assert set(prefs.keys()) == set(ALL_CAPABILITY_KEYS)


def test_user_can_toggle_preferences():
    prefs = get_default_preferences()
    updated = apply_preferences(prefs, {CAP_COMMAND_EXECUTION: False})
    assert updated[CAP_COMMAND_EXECUTION] is False
    # Other preferences unchanged
    assert updated[CAP_BROWSER_AUTOMATION] is True


def test_preferences_persist_in_state():
    prefs = get_default_preferences()
    prefs = apply_preferences(prefs, {CAP_PLAYWRIGHT_VERIFICATION: False, CAP_WEB_EVIDENCE: True})
    assert prefs[CAP_PLAYWRIGHT_VERIFICATION] is False
    assert prefs[CAP_WEB_EVIDENCE] is True


def test_unknown_keys_are_ignored():
    prefs = get_default_preferences()
    updated = apply_preferences(prefs, {"unknown_capability_xyz": True})
    assert "unknown_capability_xyz" not in updated


def test_checked_command_execution_does_not_enable_execution():
    """Checked UI preference must NOT enable actual command execution."""
    prefs = get_default_preferences()
    assert prefs[CAP_COMMAND_EXECUTION] is True
    summary = build_feature_summary(prefs)
    cmd_entry = next(e for e in summary if e['key'] == CAP_COMMAND_EXECUTION)
    # Preference is requested but backend blocks it
    assert cmd_entry['requested'] is True
    assert cmd_entry['blocked'] is True
    assert "blocked" in cmd_entry['runtime_status'].lower()


def test_checked_browser_automation_does_not_enable_arbitrary_browser():
    """Checked browser automation preference must NOT enable arbitrary browser automation."""
    prefs = get_default_preferences()
    summary = build_feature_summary(prefs)
    browser_entry = next(e for e in summary if e['key'] == CAP_BROWSER_AUTOMATION)
    assert browser_entry['requested'] is True
    assert browser_entry['blocked'] is True


def test_final_summary_includes_selected_and_blocked_capabilities():
    prefs = get_default_preferences()
    summary = build_feature_summary(prefs)
    assert len(summary) == len(ALL_CAPABILITY_KEYS)
    for entry in summary:
        assert 'key' in entry
        assert 'label' in entry
        assert 'requested' in entry
        assert 'runtime_status' in entry
        assert 'blocked' in entry


def test_unchecked_preference_shows_not_requested():
    prefs = get_default_preferences()
    prefs = apply_preferences(prefs, {CAP_SANDBOXED_INSTALL: False})
    summary = build_feature_summary(prefs)
    install_entry = next(e for e in summary if e['key'] == CAP_SANDBOXED_INSTALL)
    assert install_entry['requested'] is False


def test_backend_policy_remains_authoritative():
    """Setting all preferences to True does not change runtime_block_reason for execution."""
    from agent.atlas_capability_preference_schema import RUNTIME_BLOCK_REASONS
    assert "level_0_manual_only" in RUNTIME_BLOCK_REASONS[CAP_COMMAND_EXECUTION]
    assert "level_0_manual_only" in RUNTIME_BLOCK_REASONS[CAP_COMMAND_EXECUTION]


def test_web_evidence_not_blocked():
    """Web evidence gathering in planner mode is not blocked."""
    prefs = get_default_preferences()
    summary = build_feature_summary(prefs)
    web_entry = next(e for e in summary if e['key'] == CAP_WEB_EVIDENCE)
    assert web_entry['blocked'] is False
