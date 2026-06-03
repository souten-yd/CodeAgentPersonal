from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from app.server import create_app
from agent.atlas_automation_features import (
    DEFAULT_AUTOMATION_FEATURES,
    DEFAULT_SELECTED_PRESET_ID,
    get_default_automation_features,
    load_full_automation_state,
    load_automation_features,
    normalize_features,
    normalize_selected_preset_id,
    resolve_features,
    save_full_automation_state,
    save_automation_features,
)
from agent.atlas_automation_profile_resolver import PRESETS
from agent.atlas_capability_preference_schema import get_default_preferences


def test_defaults_are_ask_pause_block():
    d = get_default_automation_features()
    assert d == {
        "critical_handling": "ask",
        "clarification_mode": "pause",
        "quality_gate_enforcement": "block",
        "requirement_coverage_enforcement": "warn",
    }
    assert d == DEFAULT_AUTOMATION_FEATURES


def test_normalize_drops_unknown_keys_and_invalid_values():
    out = normalize_features({"critical_handling": "block", "clarification_mode": "nonsense", "bogus": "x"})
    assert out["critical_handling"] == "block"
    assert out["clarification_mode"] == "pause"  # invalid -> default
    assert "bogus" not in out


def test_save_and_load_roundtrip(tmp_path: Path):
    saved = save_automation_features(tmp_path, {
        "critical_handling": "auto",
        "quality_gate_enforcement": "warn",
        "requirement_coverage_enforcement": "enforce",
    })
    assert saved["critical_handling"] == "auto"
    assert saved["quality_gate_enforcement"] == "warn"
    assert saved["requirement_coverage_enforcement"] == "enforce"
    loaded = load_automation_features(tmp_path)
    assert loaded["critical_handling"] == "auto"
    assert loaded["quality_gate_enforcement"] == "warn"
    assert loaded["requirement_coverage_enforcement"] == "enforce"
    assert loaded["clarification_mode"] == "pause"


def test_load_missing_returns_defaults(tmp_path: Path):
    assert load_automation_features(tmp_path) == get_default_automation_features()


def test_resolve_prefers_request_override(tmp_path: Path):
    save_automation_features(tmp_path, {"critical_handling": "block"})
    out = resolve_features(request_features={"critical_handling": "auto"}, ca_data_root=tmp_path)
    assert out["critical_handling"] == "auto"  # request override wins
    out2 = resolve_features(ca_data_root=tmp_path)
    assert out2["critical_handling"] == "block"  # server-side default


def test_full_state_defaults_and_roundtrip(tmp_path: Path):
    state = load_full_automation_state(tmp_path)
    assert state["selected_preset_id"] == DEFAULT_SELECTED_PRESET_ID
    assert state["capability_preferences"] == get_default_preferences()

    saved = save_full_automation_state(
        tmp_path,
        features={"critical_handling": "block"},
        selected_preset_id="supervised_auto",
        capability_preferences={"cap-command-execution": False, "cap-web-evidence": True},
    )

    assert saved["features"]["critical_handling"] == "block"
    assert saved["selected_preset_id"] == "supervised_auto"
    assert saved["capability_preferences"]["command_execution_requested"] is False
    assert saved["capability_preferences"]["web_evidence_gathering_requested"] is True
    assert load_automation_features(tmp_path)["critical_handling"] == "block"


def test_default_preset_is_a_known_claude_style_preset():
    # The default must exist in the canonical preset catalogue (not Vue / Atlas Next)
    # and must preserve the full-automatic code generation configuration.
    assert DEFAULT_SELECTED_PRESET_ID in PRESETS
    assert DEFAULT_SELECTED_PRESET_ID == "autonomous_bounded_dev"


def test_normalize_selected_preset_id_none_falls_back_to_default():
    assert normalize_selected_preset_id(None) == DEFAULT_SELECTED_PRESET_ID
    assert normalize_selected_preset_id("") == DEFAULT_SELECTED_PRESET_ID
    assert normalize_selected_preset_id("   ") == DEFAULT_SELECTED_PRESET_ID


def test_normalize_selected_preset_id_unknown_fails_closed():
    # Unknown ids fail closed to the default instead of being stored verbatim.
    assert normalize_selected_preset_id("vue_atlas_next") == DEFAULT_SELECTED_PRESET_ID
    assert normalize_selected_preset_id("definitely-not-a-preset") == DEFAULT_SELECTED_PRESET_ID
    # Known ids round-trip unchanged.
    assert normalize_selected_preset_id("supervised_auto") == "supervised_auto"


def test_load_full_state_with_no_state_file_returns_default(tmp_path: Path):
    state = load_full_automation_state(tmp_path)
    assert state["selected_preset_id"] == DEFAULT_SELECTED_PRESET_ID
    assert state["features"] == get_default_automation_features()
    assert state["capability_preferences"] == get_default_preferences()


def test_malformed_state_file_fails_closed_not_500(tmp_path: Path):
    path = tmp_path / "atlas" / "automation_features.json"
    path.parent.mkdir(parents=True)
    path.write_text("{ this is not valid json ", encoding="utf-8")

    state = load_full_automation_state(tmp_path)
    assert state["selected_preset_id"] == DEFAULT_SELECTED_PRESET_ID
    assert state["features"] == get_default_automation_features()


def test_state_file_without_selected_preset_id_uses_default(tmp_path: Path):
    path = tmp_path / "atlas" / "automation_features.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"features": {"critical_handling": "auto"}}', encoding="utf-8")

    state = load_full_automation_state(tmp_path)
    assert state["features"]["critical_handling"] == "auto"
    assert state["selected_preset_id"] == DEFAULT_SELECTED_PRESET_ID


def test_full_auto_preset_round_trips(tmp_path: Path):
    # The full-automatic code generation preset must survive a save/load cycle.
    saved = save_full_automation_state(tmp_path, selected_preset_id="autonomous_bounded_dev")
    assert saved["selected_preset_id"] == "autonomous_bounded_dev"
    assert load_full_automation_state(tmp_path)["selected_preset_id"] == "autonomous_bounded_dev"


def test_api_get_returns_200_with_malformed_state(tmp_path: Path):
    path = tmp_path / "atlas" / "automation_features.json"
    path.parent.mkdir(parents=True)
    path.write_text("not-json-at-all", encoding="utf-8")

    app = create_app()
    app.state.atlas_ca_data_root = str(tmp_path)
    client = TestClient(app)

    resp = client.get("/api/atlas/automation-features")
    assert resp.status_code == 200
    body = resp.json()
    assert body["selected_preset_id"] == DEFAULT_SELECTED_PRESET_ID
    assert "capability_preferences" in body


def test_load_old_flat_json_as_features(tmp_path: Path):
    path = tmp_path / "atlas" / "automation_features.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"critical_handling": "auto"}', encoding="utf-8")

    state = load_full_automation_state(tmp_path)

    assert state["features"]["critical_handling"] == "auto"
    assert state["selected_preset_id"] == "autonomous_bounded_dev"


def test_automation_features_api_roundtrip_new_keys(tmp_path: Path):
    app = create_app()
    app.state.atlas_ca_data_root = str(tmp_path)
    client = TestClient(app)

    initial = client.get("/api/atlas/automation-features").json()
    assert initial["selected_preset_id"] == "autonomous_bounded_dev"

    saved = client.post(
        "/api/atlas/automation-features",
        json={
            "features": {"quality_gate_enforcement": "warn"},
            "selected_preset_id": "supervised_auto",
            "capability_preferences": {"cap-command-execution": False},
        },
    ).json()

    assert saved["features"]["quality_gate_enforcement"] == "warn"
    assert saved["selected_preset_id"] == "supervised_auto"
    assert saved["capability_preferences"]["command_execution_requested"] is False
    loaded = client.get("/api/atlas/automation-features").json()
    assert loaded["selected_preset_id"] == "supervised_auto"
