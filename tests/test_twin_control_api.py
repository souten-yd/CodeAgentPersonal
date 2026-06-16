"""G2 — Twin Control API: settings read/change, profiles, capability evaluation."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.server import create_app


def _client(tmp_path):
    app = create_app()
    app.state.atlas_ca_data_root = str(tmp_path)
    return TestClient(app)


def test_get_settings_defaults(tmp_path, monkeypatch):
    for e in ("ATLAS_TWIN_PIPELINE_MODE", "ATLAS_TWIN_GATE_BLOCKING", "ATLAS_TWIN_BLOCK_UNVERIFIED",
              "ATLAS_TWIN_BLOCK_SCHEMA", "ATLAS_TWIN_BUILD_PROJECT"):
        monkeypatch.delenv(e, raising=False)
    r = _client(tmp_path).get("/api/twin/settings")
    assert r.status_code == 200
    s = r.json()
    assert s["mode"] == "active" and s["gate_blocking"] is True
    assert s["block_schema"] is False and s["build_project"] is False


def test_post_settings_changes_and_is_reversible(tmp_path, monkeypatch):
    for e in ("ATLAS_TWIN_PIPELINE_MODE", "ATLAS_TWIN_BLOCK_SCHEMA"):
        monkeypatch.delenv(e, raising=False)
    c = _client(tmp_path)
    out = c.post("/api/twin/settings", json={"mode": "off", "block_schema": True}).json()
    assert out["mode"] == "off" and out["block_schema"] is True
    # Reversible.
    back = c.post("/api/twin/settings", json={"mode": "active", "block_schema": False}).json()
    assert back["mode"] == "active" and back["block_schema"] is False


def test_post_settings_rejects_bad_mode(tmp_path):
    r = _client(tmp_path).post("/api/twin/settings", json={"mode": "banana"})
    assert r.status_code == 400


def test_get_profiles_reflects_capability_store(tmp_path):
    # Seed a capability profile with a weakness.
    from agent.model_forge.profile_store import ProfileStore
    ProfileStore(Path(tmp_path) / "model_forge" / "profiles").record_observation(
        model_id="m1", provider_id="local",
        dimensions={"flag_reasoning": 0.2, "impact_analysis": 0.9}, evidence_refs=["e"])
    r = _client(tmp_path).get("/api/twin/profiles")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 1
    prof = data["profiles"][0]
    assert prof["model_id"] == "m1"
    assert "flag_reasoning" in prof["known_weaknesses"]


def test_evaluate_unavailable_when_model_down(tmp_path):
    # Point at an unreachable server -> unavailable, records nothing (never fabricates).
    r = _client(tmp_path).post("/api/twin/evaluate",
                               json={"model_id": "m1", "base_url": "http://127.0.0.1:1"})
    assert r.status_code == 200
    out = r.json()
    assert out["verdict"] == "unavailable" and out["recorded"] is False
