"""PFG-19 — Forge backend API tests.

Proves: every endpoint responds, secrets are never returned, disabled/unavailable
provider states are visible, stage cutover needs acknowledgement (409), and unsafe
route policy is refused (400).
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.model_forge.providers.openrouter_catalog import OpenRouterCatalogResult
from agent.model_forge.schema import ModelDescriptor, SourceClass
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
    for provider in providers:
        assert provider["configured_state"] in ("disabled", "missing_config", "configured")
        assert provider["runtime_health"] in ("not_probed", "ready", "unavailable", "error")


def test_local_provider_configured_state_is_not_runtime_ready_until_probe(tmp_path):
    c = _client(tmp_path)
    c.post("/api/forge/settings", json={
        "local_provider": {"base_url": "http://127.0.0.1:1", "model_id": "m-local"},
    })
    local = next(
        p for p in c.get("/api/forge/providers").json()["providers"]
        if p["provider_id"] == "local_openai_compatible"
    )
    assert local["configured_state"] == "configured"
    assert local["runtime_health"] == "not_probed"
    assert local["health"] == "unavailable"
    assert local["health_detail"] == "runtime_not_probed"


def test_provider_probe_endpoint_is_explicit_and_records_failure(tmp_path):
    c = _client(tmp_path)
    c.post("/api/forge/settings", json={
        "local_provider": {"base_url": "http://127.0.0.1:1", "model_id": "m-local"},
    })
    probed = c.post("/api/forge/providers/local_openai_compatible/probe").json()["provider"]
    assert probed["runtime_health"] in ("unavailable", "error")
    local = next(
        p for p in c.get("/api/forge/providers").json()["providers"]
        if p["provider_id"] == "local_openai_compatible"
    )
    assert local["runtime_health"] in ("unavailable", "error")
    assert local["last_probe_error"]


def test_provider_probe_without_local_base_url_is_offline_safe(tmp_path):
    c = _client(tmp_path)
    probed = c.post("/api/forge/providers/local_openai_compatible/probe").json()["provider"]
    assert probed["configured_state"] == "missing_config"
    assert probed["runtime_health"] == "unavailable"
    assert probed["last_probe_error"] == "missing_base_url"


def test_presets_and_models_and_profiles_and_leaderboard(tmp_path):
    c = _client(tmp_path)
    assert isinstance(c.get("/api/forge/presets").json()["presets"], list)
    assert c.get("/api/forge/presets").json()["presets"]  # built-ins exist
    assert c.get("/api/forge/models").json()["models"] == []
    assert c.get("/api/forge/profiles").json()["profiles"] == []
    assert c.get("/api/forge/leaderboard").json()["leaderboard"] == []


def test_settings_persist_safe_provider_config_and_reject_secret_values(tmp_path):
    c = _client(tmp_path)
    saved = c.post("/api/forge/settings", json={
        "local_provider": {
            "base_url": "http://127.0.0.1:8080/v1",
            "model_id": "local-model",
            "model_storage_dir": "D:/models",
        },
        "openrouter": {
            "enabled": True,
            "api_key_env": "OPENROUTER_API_KEY",
            "base_url": "https://openrouter.ai/api/v1",
        },
    })
    assert saved.status_code == 200
    settings = c.get("/api/forge/settings").json()["settings"]
    assert settings["local_provider"]["model_storage_dir"] == "D:/models"
    assert settings["openrouter"]["enabled"] is True
    blob = str(settings).lower()
    assert "sk-" not in blob and "authorization" not in blob

    rejected = c.post("/api/forge/settings", json={
        "openrouter": {"api_key": "sk-do-not-store"},
    })
    assert rejected.status_code == 400
    assert rejected.json()["detail"] == "secret_values_must_not_be_persisted"


def test_local_provider_runtime_kind_roundtrips_and_defaults_to_llama_cpp(tmp_path):
    c = _client(tmp_path)
    # Default when unspecified.
    c.post("/api/forge/settings", json={"local_provider": {"base_url": "http://127.0.0.1:8080/v1"}})
    assert c.get("/api/forge/settings").json()["settings"]["local_provider"]["runtime_kind"] == "llama_cpp"
    # LM Studio runtime persists.
    c.post("/api/forge/settings", json={
        "local_provider": {"base_url": "http://127.0.0.1:1234/v1", "runtime_kind": "lm_studio"},
    })
    assert c.get("/api/forge/settings").json()["settings"]["local_provider"]["runtime_kind"] == "lm_studio"
    # An unknown runtime kind is normalised back to the safe default rather than persisted verbatim.
    c.post("/api/forge/settings", json={"local_provider": {"runtime_kind": "bogus"}})
    assert c.get("/api/forge/settings").json()["settings"]["local_provider"]["runtime_kind"] == "llama_cpp"


def test_local_catalog_parses_openai_models_shape(tmp_path):
    from agent.model_forge.forge_service import ForgeService

    def fake_get(url, _timeout):
        assert url.endswith("/v1/models")
        assert "/v1/v1/" not in url  # base_url must be host root, not already include /v1
        return 200, '{"data": [{"id": "Mistral-Small.gguf"}, {"id": "Qwen.gguf"}], "object": "list"}'

    out = ForgeService(tmp_path).local_catalog(base_url="http://127.0.0.1:8080", runtime_kind="lm_studio", http_get=fake_get)
    assert out["status"] == "ready"
    assert out["runtime_kind"] == "lm_studio"
    assert [m["model_id"] for m in out["models"]] == ["Mistral-Small.gguf", "Qwen.gguf"]


def test_local_catalog_unreachable_is_graceful(tmp_path):
    from agent.model_forge.forge_service import ForgeService

    def boom(_url, _timeout):
        raise ConnectionError("refused")

    out = ForgeService(tmp_path).local_catalog(base_url="http://127.0.0.1:9", http_get=boom)
    assert out["status"] == "unreachable"
    assert out["models"] == []


def test_local_catalog_endpoint_returns_shape(tmp_path):
    body = _client(tmp_path).get("/api/forge/local-catalog?runtime_kind=lm_studio").json()
    assert "models" in body and isinstance(body["models"], list)
    assert "status" in body and "base_url" in body


def test_settings_reports_credential_state_without_returning_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-secret-value")
    settings = _client(tmp_path).get("/api/forge/settings").json()["settings"]
    assert settings["openrouter"]["credential_configured"] is True
    assert "sk-secret-value" not in str(settings)


def test_openrouter_catalog_endpoint_serves_cache_without_key_and_models_include_cache(tmp_path):
    cache = tmp_path / "model_forge" / "catalog" / "openrouter_models.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    cached = OpenRouterCatalogResult(
        status="fetched",
        models=[
            ModelDescriptor(
                provider_id="openrouter",
                model_id="anthropic/claude",
                display_name="Claude",
                source_class=SourceClass.EXTERNAL_CLOUD,
            )
        ],
        fetched_at="2026-06-12T00:00:00+00:00",
    )
    cache.write_text(cached.model_dump_json(), encoding="utf-8")

    c = _client(tmp_path)
    catalog = c.get("/api/forge/providers/openrouter/catalog").json()
    assert catalog["status"] == "from_cache"
    assert catalog["from_cache"] is True
    assert catalog["credential_configured"] is False
    assert catalog["models"][0]["model_id"] == "anthropic/claude"
    assert "sk-" not in str(catalog).lower()

    models = c.get("/api/forge/models").json()["models"]
    assert {
        "provider_id": "openrouter",
        "model_id": "anthropic/claude",
        "display_name": "Claude",
        "source": "openrouter_catalog_cache",
    } in models


def test_openrouter_catalog_endpoint_reports_disabled_without_cache_or_live_call(tmp_path):
    body = _client(tmp_path).get("/api/forge/providers/openrouter/catalog").json()
    assert body["status"] == "disabled"
    assert body["reason"] in ("local_only_blocks_external", "openrouter_disabled")
    assert body["models"] == []


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
