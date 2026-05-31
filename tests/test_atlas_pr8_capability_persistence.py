from __future__ import annotations

import tempfile

from agent.atlas_capability_preference_schema import (
    CAP_BROWSER_AUTOMATION,
    CAP_COMMAND_EXECUTION,
    apply_preferences,
    build_feature_summary,
    get_default_preferences,
    normalize_ui_preferences,
)


# ── UI-id normalization ───────────────────────────────────────────────────────

def test_normalize_maps_ui_ids_to_backend_keys():
    incoming = {
        "cap-command-execution": True,
        "cap-browser-automation": False,
        "cap-playwright-verification": True,
        "cap-web-evidence": True,
        "cap-sandboxed-install": False,
    }
    out = normalize_ui_preferences(incoming)
    assert out[CAP_COMMAND_EXECUTION] is True
    assert out[CAP_BROWSER_AUTOMATION] is False
    assert "command_execution_requested" in out


def test_normalize_accepts_backend_keys_too():
    out = normalize_ui_preferences({"command_execution_requested": False})
    assert out[CAP_COMMAND_EXECUTION] is False


def test_normalize_ignores_unknown_keys():
    out = normalize_ui_preferences({"cap-unknown-xyz": True})
    assert out == {}


# ── Persistence + authority ───────────────────────────────────────────────────

def test_checked_command_pref_does_not_enable_execution():
    prefs = apply_preferences(get_default_preferences(),
                              normalize_ui_preferences({"cap-command-execution": True}))
    summary = build_feature_summary(prefs)
    cmd = next(e for e in summary if e["key"] == CAP_COMMAND_EXECUTION)
    assert cmd["requested"] is True
    assert cmd["blocked"] is True  # backend policy blocks despite preference
    assert "blocked" in cmd["runtime_status"].lower()


def test_checked_browser_pref_does_not_enable_arbitrary_browser():
    prefs = apply_preferences(get_default_preferences(),
                              normalize_ui_preferences({"cap-browser-automation": True}))
    summary = build_feature_summary(prefs)
    browser = next(e for e in summary if e["key"] == CAP_BROWSER_AUTOMATION)
    assert browser["requested"] is True
    assert browser["blocked"] is True


# ── End-to-end via the create-plan-pool API (sync) ────────────────────────────

def test_capability_preferences_persist_to_pool_metadata():
    import main
    from fastapi.testclient import TestClient

    d = tempfile.mkdtemp()
    main.app.state.atlas_ca_data_dir = d
    main.app.state.atlas_llm_json_fn = None
    c = TestClient(main.app)
    r = c.post(
        "/api/atlas/plan-pools?sync=1",
        json={
            "input": "build a small page",
            "capability_preferences": {"cap-command-execution": False, "cap-web-evidence": True},
        },
    )
    assert r.status_code == 200
    md = r.json().get("plan_pool", {}).get("metadata", {})
    prefs = md.get("feature_preferences", {})
    # user unchecked command execution → stored as False
    assert prefs.get("command_execution_requested") is False
    # default-checked for others
    assert prefs.get("web_evidence_gathering_requested") is True
    # feature_summary present with blocked command execution
    summary = md.get("feature_summary", [])
    cmd = next((e for e in summary if e["key"] == "command_execution_requested"), None)
    assert cmd is not None
    assert cmd["blocked"] is True


def test_capability_preferences_default_all_checked_when_absent():
    import main
    from fastapi.testclient import TestClient

    d = tempfile.mkdtemp()
    main.app.state.atlas_ca_data_dir = d
    main.app.state.atlas_llm_json_fn = None
    c = TestClient(main.app)
    r = c.post("/api/atlas/plan-pools?sync=1", json={"input": "build a small page"})
    assert r.status_code == 200
    prefs = r.json().get("plan_pool", {}).get("metadata", {}).get("feature_preferences", {})
    # absent → defaults all checked
    assert prefs.get("command_execution_requested") is True
    assert prefs.get("browser_automation_requested") is True
