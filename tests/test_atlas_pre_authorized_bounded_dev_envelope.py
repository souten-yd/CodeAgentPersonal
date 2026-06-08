from __future__ import annotations

import pytest

from app.atlas.automation_safety_profile import (
    PROFILE_AUTONOMOUS_DEV_AGENT,
    SELF_SCOPE_ATLAS_RUNTIME_STRICT,
    SELF_SCOPE_NONE,
)
from app.atlas.pre_authorized_bounded_dev_envelope import (
    ALLOWED_ENVELOPES,
    ENVELOPE_BOUNDED_DEV,
    ENVELOPE_NONE,
    ENVELOPE_SELF_IMPROVEMENT,
    SCHEMA_VERSION,
    TRACK_PR,
    build_envelope_manifest,
    get_envelope,
    list_envelopes,
)


def test_allowed_envelopes_are_stable() -> None:
    assert ALLOWED_ENVELOPES == frozenset(
        {ENVELOPE_NONE, ENVELOPE_BOUNDED_DEV, ENVELOPE_SELF_IMPROVEMENT}
    )


def test_list_envelopes_returns_all_recipes() -> None:
    envelopes = list_envelopes()
    by_id = {item["envelope_id"]: item for item in envelopes}
    assert set(by_id) == ALLOWED_ENVELOPES
    assert by_id[ENVELOPE_NONE]["autonomous_loop_execution_enabled"] is False
    assert by_id[ENVELOPE_BOUNDED_DEV]["autonomous_loop_execution_enabled"] is True
    assert by_id[ENVELOPE_BOUNDED_DEV]["self_improvement_enabled"] is False
    assert by_id[ENVELOPE_SELF_IMPROVEMENT]["self_improvement_enabled"] is True
    assert by_id[ENVELOPE_SELF_IMPROVEMENT]["self_improvement_scope"] == SELF_SCOPE_ATLAS_RUNTIME_STRICT


def test_get_envelope_unknown_returns_blocked() -> None:
    envelope = get_envelope("does_not_exist")
    assert envelope["status"] == "blocked"
    assert "envelope_unknown" in envelope["blocking_reasons"]
    assert envelope["autonomous_loop_execution_enabled"] is False


def test_get_envelope_bounded_dev_has_bounds() -> None:
    envelope = get_envelope(ENVELOPE_BOUNDED_DEV)
    assert envelope["schema_version"] == SCHEMA_VERSION
    assert envelope["track_pr"] == TRACK_PR
    assert envelope["status"] == "active"
    bounds = envelope["bounds"]
    assert bounds["max_actions_per_loop"] > 0
    assert bounds["max_files_changed"] > 0
    assert bounds["max_runtime_seconds"] > 0
    # Dev work allows the whole selected-project work root via the "." sentinel; blocked_paths
    # still guard dangerous locations.
    assert bounds["allowed_paths"] == ["."]
    assert ".git/" in bounds["blocked_paths"]
    assert any("pytest" in cmd for cmd in bounds["command_allowlist"])


def test_envelope_bounded_dev_does_not_enable_self_improvement() -> None:
    envelope = get_envelope(ENVELOPE_BOUNDED_DEV)
    assert envelope["self_improvement_enabled"] is False
    assert envelope["automatic_self_improvement_enabled"] is False
    assert envelope["self_improvement_scope"] == SELF_SCOPE_NONE


def test_envelope_self_improvement_requires_strict_gate_and_checkpoint() -> None:
    envelope = get_envelope(ENVELOPE_SELF_IMPROVEMENT)
    assert envelope["strict_gate_required"] is True
    assert envelope["level4_checkpoint_required"] is True
    assert envelope["candidate_workspace_required"] is True


def test_build_envelope_manifest_blocks_when_safety_profile_inactive() -> None:
    manifest = build_envelope_manifest(
        envelope_id=ENVELOPE_BOUNDED_DEV,
        safety_profile={"status": "blocked"},
        confirmation_text="SELECT AUTOMATION PROFILE",
        created_at="2026-05-28T00:00:00+00:00",
    )
    assert manifest["status"] == "blocked"
    assert "safety_profile_not_active" in manifest["blocking_reasons"]
    assert manifest["autonomous_loop_execution_enabled"] is False


def test_build_envelope_manifest_blocks_without_confirmation_text() -> None:
    safety_profile = {
        "status": "active",
        "profile_id": "p1",
        "automation_safety_profile": PROFILE_AUTONOMOUS_DEV_AGENT,
        "self_improvement_enabled": False,
        "self_improvement_scope": SELF_SCOPE_NONE,
    }
    manifest = build_envelope_manifest(
        envelope_id=ENVELOPE_BOUNDED_DEV,
        safety_profile=safety_profile,
        confirmation_text="wrong text",
        created_at="2026-05-28T00:00:00+00:00",
    )
    assert manifest["status"] == "blocked"
    assert "confirmation_text_required" in manifest["blocking_reasons"]


def test_build_envelope_manifest_active_for_bounded_dev() -> None:
    safety_profile = {
        "status": "active",
        "profile_id": "safety_profile_1",
        "automation_safety_profile": PROFILE_AUTONOMOUS_DEV_AGENT,
        "self_improvement_enabled": False,
        "self_improvement_scope": SELF_SCOPE_NONE,
        "strict_gate_approved": False,
    }
    manifest = build_envelope_manifest(
        envelope_id=ENVELOPE_BOUNDED_DEV,
        safety_profile=safety_profile,
        confirmation_text="SELECT AUTOMATION PROFILE",
        created_at="2026-05-28T00:00:00+00:00",
    )
    assert manifest["status"] == "active"
    assert manifest["blocking_reasons"] == []
    assert manifest["autonomous_loop_execution_enabled"] is True
    assert manifest["automatic_patch_apply_enabled"] is True
    assert manifest["automatic_self_improvement_enabled"] is False
    assert manifest["safety_profile_id"] == "safety_profile_1"
    assert manifest["draft_pr_only"] is True


def test_build_envelope_manifest_legacy_confirmation_accepted() -> None:
    safety_profile = {
        "status": "active",
        "profile_id": "safety_profile_legacy",
        "automation_safety_profile": PROFILE_AUTONOMOUS_DEV_AGENT,
        "self_improvement_enabled": False,
        "self_improvement_scope": SELF_SCOPE_NONE,
    }
    manifest = build_envelope_manifest(
        envelope_id=ENVELOPE_BOUNDED_DEV,
        safety_profile=safety_profile,
        confirmation_text="SELECT AUTOMATION SAFETY PROFILE",
        created_at="2026-05-28T00:00:00+00:00",
    )
    assert manifest["confirmation_text_accepted"] is True
    assert manifest["status"] == "active"


def test_build_envelope_manifest_self_improvement_requires_strict_gate() -> None:
    safety_profile = {
        "status": "active",
        "profile_id": "p2",
        "automation_safety_profile": PROFILE_AUTONOMOUS_DEV_AGENT,
        "self_improvement_enabled": True,
        "self_improvement_scope": SELF_SCOPE_ATLAS_RUNTIME_STRICT,
        "strict_gate_approved": False,
        "level4_checkpoint_path": "",
    }
    manifest = build_envelope_manifest(
        envelope_id=ENVELOPE_SELF_IMPROVEMENT,
        safety_profile=safety_profile,
        confirmation_text="SELECT AUTOMATION PROFILE",
        created_at="2026-05-28T00:00:00+00:00",
    )
    assert manifest["status"] == "blocked"
    assert "strict_gate_required_by_envelope" in manifest["blocking_reasons"]
    assert "level4_checkpoint_required_by_envelope" in manifest["blocking_reasons"]


def test_build_envelope_manifest_blocks_safety_profile_mismatch() -> None:
    safety_profile = {
        "status": "active",
        "profile_id": "p3",
        "automation_safety_profile": "review_only",
        "self_improvement_enabled": False,
        "self_improvement_scope": SELF_SCOPE_NONE,
    }
    manifest = build_envelope_manifest(
        envelope_id=ENVELOPE_BOUNDED_DEV,
        safety_profile=safety_profile,
        confirmation_text="SELECT AUTOMATION PROFILE",
        created_at="2026-05-28T00:00:00+00:00",
    )
    assert manifest["status"] == "blocked"
    assert "safety_profile_mismatch" in manifest["blocking_reasons"]
