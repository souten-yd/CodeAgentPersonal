"""PR-9c: Tests ensuring manifest and workflow_state_contract are aligned."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.atlas.workflow_state_contract import build_read_only_workflow_state

_MANIFEST_PATH = Path(__file__).parent.parent / "docs" / "atlas_automation_phase_manifest.json"

_BASE_KWARGS = dict(
    goal="test goal",
    project_path="/tmp/test",
    phase="test_phase",
    status="ok",
    primary_cta_label="Run",
)


def _load_manifest() -> dict:
    with _MANIFEST_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _build(**kwargs) -> dict:
    kw = dict(_BASE_KWARGS)
    kw.update(kwargs)
    return build_read_only_workflow_state(**kw)


# --- Drift prevention ---

def test_canonical_runtime_level_matches_manifest():
    manifest = _load_manifest()
    payload = _build()
    assert payload["canonical_runtime_level"] == manifest["current_level"]


def test_canonical_autonomous_execution_matches_manifest():
    manifest = _load_manifest()
    payload = _build()
    assert payload["canonical_autonomous_execution_enabled"] == manifest["autonomous_execution_enabled"]


def test_contract_scope_is_vue_preview():
    payload = _build()
    assert payload["contract_scope"] == "vue_next_preview_read_only"


def test_preview_and_canonical_levels_are_distinct():
    payload = _build()
    assert payload["preview_runtime_level"] == "level_0_manual_only"
    assert payload["canonical_runtime_level"] != "level_0_manual_only"


# --- UI actions read-only ---

def test_all_available_actions_are_disabled():
    payload = _build(available_actions=[{"id": "a", "label": "Run", "kind": "execute"}])
    for action in payload["available_actions"]:
        assert action["enabled"] is False
        assert action["read_only"] is True


def test_primary_cta_is_disabled():
    payload = _build()
    assert payload["primary_cta"]["enabled"] is False
    assert payload["primary_cta"]["read_only"] is True


def test_safety_flags_all_false():
    payload = _build()
    safety = payload["safety"]
    for key, val in safety.items():
        if isinstance(val, bool) and (key.endswith("_enabled") or "_automatic_" in key):
            assert val is False, f"safety[{key!r}] should be False but is True"


# --- Capability preferences remain metadata-only ---

def test_capability_preferences_do_not_enable_command_execution():
    payload = _build()
    assert payload["autonomous_execution_enabled"] is False
    assert payload["level1_execution_enabled"] is False
    assert payload.get("vue_execution_enabled") is False


def test_manifest_vue_next_preview_contract_fields():
    manifest = _load_manifest()
    assert manifest["vue_next_preview_contract_scope"] == "read_only_display_only"
    assert manifest["vue_next_preview_level_is_level0"] is True
    assert manifest["vue_next_preview_all_actions_disabled"] is True

# --- UI default wording / removed Vue runtime cleanup ---

def test_manifest_keeps_buildless_shell_as_active_default():
    manifest = _load_manifest()
    assert manifest["active_ui_default_policy"] == "buildless_thinux_fastui_conversational_shell"
    assert manifest["default_conversational_shell_requires_build"] is False
    assert manifest["default_conversational_shell_requires_vue"] is False
    assert manifest["default_conversational_shell_requires_vite"] is False


def test_manifest_marks_vue_default_metadata_deprecated_non_active():
    manifest = _load_manifest()
    stale_active_keys = [key for key in manifest if key.startswith("vue_default_")]
    assert stale_active_keys == []
    assert manifest["deprecated_vue_default_metadata_status"] == "deprecated_non_active_historical_record"
    assert manifest["deprecated_vue_default_metadata_active"] is False
    assert manifest["deprecated_vue_default_route_was"] == "/"
    assert "removed" in manifest["deprecated_vue_default_metadata_reason"]


def test_removed_atlas_next_vue_runtime_has_no_server_serving_path():
    route_text = (Path(__file__).parent.parent / "main.py").read_text(encoding="utf-8")
    server_text = (Path(__file__).parent.parent / "app" / "server.py").read_text(encoding="utf-8")
    combined = route_text + "\n" + server_text
    forbidden = [
        "configure_atlas_next_preview_route",
        "web/atlas-next/dist",
        "ATLAS_NEXT_DEFAULT_ENABLED",
        "validate_atlas_next_dist",
    ]
    for token in forbidden:
        assert token not in combined
    assert '@app.get("/atlas-next' not in route_text
    assert 'app.mount("/atlas-next' not in combined
    assert "atlas-next" not in combined
