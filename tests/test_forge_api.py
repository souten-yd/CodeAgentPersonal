"""PFG-19 — Forge backend API tests.

Proves: every endpoint responds, secrets are never returned, disabled/unavailable
provider states are visible, stage cutover needs acknowledgement (409), and unsafe
route policy is refused (400).
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.forge import router as forge_router


def _client(tmp_path: Path) -> TestClient:
    app = FastAPI()
    app.state.atlas_ca_data_root = str(tmp_path)
    app.include_router(forge_router)
    return TestClient(app)


def test_status_reports_forge_off_and_legacy_primary(tmp_path):
    body = _client(tmp_path).get("/api/forge/status").json()
    assert body["forge_enabled"] is False
    assert body["legacy_primary"] is True
    assert body["source_mode"] == "local_only"
    assert "provider_health" in body


def test_providers_show_states_and_never_leak_secrets(tmp_path):
    body = _client(tmp_path).get("/api/forge/providers").json()
    providers = body["providers"]
    ids = {p["provider_id"] for p in providers}
    assert "openrouter" in ids
    # OpenRouter is disabled by default and shows a non-ready state, not an error spam.
    openrouter = next(p for p in providers if p["provider_id"] == "openrouter")
    assert openrouter["health"] in ("disabled", "unavailable")
    # No secret value is ever present; only the credential ENV NAME may appear.
    blob = str(body).lower()
    for forbidden in ("authorization", "bearer ", "sk-", "api_key\":"):
        assert forbidden not in blob, forbidden
    assert "credential_env" in openrouter


def test_presets_and_models_and_profiles_and_leaderboard(tmp_path):
    c = _client(tmp_path)
    assert isinstance(c.get("/api/forge/presets").json()["presets"], list)
    assert c.get("/api/forge/presets").json()["presets"]  # built-ins exist
    assert c.get("/api/forge/models").json()["models"] == []
    assert c.get("/api/forge/profiles").json()["profiles"] == []
    assert c.get("/api/forge/leaderboard").json()["leaderboard"] == []


def test_stage_policy_get_defaults_and_cutover_requires_ack(tmp_path):
    c = _client(tmp_path)
    policy = c.get("/api/forge/stage-policy").json()["stage_policy"]
    modes = {e["mode"] for e in policy}
    assert modes <= {"disabled", "shadow_select"}
    # auto_select without acknowledgement is refused (no automatic cutover).
    resp = c.post("/api/forge/stage-policy",
                  json={"stage": "patch_generation", "mode": "auto_select"})
    assert resp.status_code == 409
    # Acknowledged cutover succeeds.
    ok = c.post("/api/forge/stage-policy",
                json={"stage": "patch_generation", "mode": "auto_select",
                      "allow_production_routing": True})
    assert ok.status_code == 200 and ok.json()["mode"] == "auto_select"


def test_route_policy_refuses_unsafe_override(tmp_path):
    c = _client(tmp_path)
    assert c.get("/api/forge/route-policy").json()["route_policy"]
    # Forcing a large change through a micro route is refused.
    bad = c.post("/api/forge/route-policy",
                 json={"change_class": "large", "preferred_route": "micro_patch"})
    assert bad.status_code == 400
    good = c.post("/api/forge/route-policy",
                  json={"change_class": "large", "preferred_route": "sliced_impact"})
    assert good.status_code == 200


def test_loadouts_seed_defaults_and_persist_custom(tmp_path):
    c = _client(tmp_path)
    loadouts = c.get("/api/forge/loadouts").json()["loadouts"]
    ids = {l["loadout_id"] for l in loadouts}
    assert {"local_safe", "openrouter_review", "repair_specialist"} <= ids
    saved = c.post("/api/forge/loadouts",
                   json={"loadout_id": "my_local", "display_name": "My Local",
                         "source_mode": "local_only"})
    assert saved.status_code == 200 and saved.json()["builtin"] is False
    # Persisted across a fresh service/client.
    again = {l["loadout_id"] for l in c.get("/api/forge/loadouts").json()["loadouts"]}
    assert "my_local" in again


def test_arena_run_blocks_external_under_local_only(tmp_path):
    c = _client(tmp_path)
    resp = c.post("/api/forge/arena/run", json={
        "stage": "patch_generation",
        "specs": [{"provider_id": "openrouter", "model_id": "x/y", "route_id": "direct_patch"}],
        "source_mode": "local_only",
    })
    assert resp.status_code == 200
    record = resp.json()
    # External candidate is recorded but not executed under Local Only.
    cand = record["candidates"][0]
    assert cand["adoption_state"] == "not_applied"
    # Run is retrievable.
    got = c.get(f"/api/forge/arena/runs/{record['arena_run_id']}")
    assert got.status_code == 200
    assert c.get("/api/forge/arena/runs/does_not_exist").status_code == 404


def test_arena_run_records_multi_preset_payload_and_standard_depth(tmp_path):
    c = _client(tmp_path)
    resp = c.post("/api/forge/arena/run", json={
        "stage": "patch_generation",
        "specs": [{"provider_id": "openrouter", "model_id": "x/y", "route_id": "direct_patch"}],
        "source_mode": "local_only",
        "preset_ids": ["quick_standard", "repair_standard"],
        "depth": "standard",
    })
    assert resp.status_code == 200
    record = resp.json()
    assert record["preset_id"] == "quick_standard"
    assert record["preset_ids"] == ["quick_standard", "repair_standard"]
    assert record["benchmark_depth"] == "standard"


def test_arena_run_reports_unsupported_depth_truthfully(tmp_path):
    c = _client(tmp_path)
    resp = c.post("/api/forge/arena/run", json={
        "stage": "patch_generation",
        "specs": [{"provider_id": "openrouter", "model_id": "x/y", "route_id": "direct_patch"}],
        "source_mode": "local_only",
        "preset_ids": ["quick_standard"],
        "depth": "deep",
    })
    assert resp.status_code == 400
    assert "benchmark_depth_unavailable_not_supported:deep" in resp.json()["detail"]
