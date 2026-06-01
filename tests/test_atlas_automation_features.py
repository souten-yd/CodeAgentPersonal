from __future__ import annotations

from pathlib import Path

from agent.atlas_automation_features import (
    DEFAULT_AUTOMATION_FEATURES,
    get_default_automation_features,
    load_automation_features,
    normalize_features,
    resolve_features,
    save_automation_features,
)


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
