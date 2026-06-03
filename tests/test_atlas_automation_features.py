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
    resolve_features,
    save_full_automation_state,
    save_automation_features,
)
from agent.atlas_capability_preference_schema import get_default_preferences


def test_defaults_are_ask_pause_block():
    d = get_default_automation_features()
    assert d == {"critical_handling": "ask", "clarification_mode": "pause", "quality_gate_enforcement": "block"}
    assert d == DEFAULT_AUTOMATION_FEATURES


def test_normalize_drops_unknown_keys_and_invalid_values():
    out = normalize_features({"critical_handling": "block", "clarification_mode": "nonsense", "bogus": "x"})
    assert out["critical_handling"] == "block"
    assert out["clarification_mode"] == "pause"  # invalid -> default
    assert "bogus" not in out


def test_save_and_load_roundtrip(tmp_path: Path):
    saved = save_automation_features(tmp_path, {"critical_handling": "auto", "quality_gate_enforcement": "warn"})
    assert saved["critical_handling"] == "auto"
    assert saved["quality_gate_enforcement"] == "warn"
    loaded = load_automation_features(tmp_path)
    assert loaded["critical_handling"] == "auto"
    assert loaded["quality_gate_enforcement"] == "warn"
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
