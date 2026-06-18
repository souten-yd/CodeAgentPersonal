"""Phase 1: Forge-evaluated model identity resolution for Atlas codegen.

resolve_active_codegen_model is the seam that attaches a Forge-evaluated (provider_id, model_id)
to a run so capability-profile-driven adaptation (route selection, decomposition tier, learned
evidence) stops being neutral. Identity only — it never changes execution routing.
"""
from __future__ import annotations

import json

from agent.model_forge.forge_service import ForgeService
from agent.model_forge.providers.local_openai_compatible import LOCAL_OPENAI_PROVIDER_ID


def _write_local_settings(tmp_path, model_id: str) -> None:
    root = tmp_path / "model_forge"
    root.mkdir(parents=True, exist_ok=True)
    (root / "settings.json").write_text(
        json.dumps({"local_provider": {"model_id": model_id, "base_url": "http://127.0.0.1:8080"}}),
        encoding="utf-8",
    )


def test_override_wins_and_reports_profile_absent(tmp_path):
    svc = ForgeService(tmp_path, env={})
    out = svc.resolve_active_codegen_model(override_provider_id="openrouter", override_model_id="anthropic/claude")
    assert out["source"] == "override"
    assert out["model_id"] == "anthropic/claude"
    assert out["provider_id"] == "openrouter"
    assert out["profile_available"] is False


def test_falls_back_to_configured_local_model_on_cold_start(tmp_path):
    # No profiles exist yet (cold start): the live :8080 model still gets a stable identity so
    # capability evidence can begin accruing across runs.
    _write_local_settings(tmp_path, "Qwen3.6-35B-A3B-UD-IQ4_XS.gguf")
    svc = ForgeService(tmp_path, env={})
    out = svc.resolve_active_codegen_model()
    assert out["source"] == "configured_local"
    assert out["provider_id"] == LOCAL_OPENAI_PROVIDER_ID
    assert out["model_id"] == "Qwen3.6-35B-A3B-UD-IQ4_XS.gguf"
    assert out["profile_available"] is False


def test_env_local_model_overrides_settings(tmp_path):
    _write_local_settings(tmp_path, "settings-model.gguf")
    svc = ForgeService(tmp_path, env={"FORGE_LOCAL_MODEL": "env-model.gguf"})
    out = svc.resolve_active_codegen_model()
    assert out["model_id"] == "env-model.gguf"
    assert out["source"] == "configured_local"


def test_stage_selection_names_profiled_candidate(tmp_path):
    # A profiled model becomes a stage-selection candidate; default PATCH_GENERATION mode
    # (shadow_select) ranks and names it without changing production routing.
    svc = ForgeService(tmp_path, env={})
    svc.profiles.record_observation(
        model_id="qwen-coder", provider_id="local_openai",
        dimensions={"patch_generation": 0.72, "overall": 0.7},
    )
    out = svc.resolve_active_codegen_model()
    assert out["source"] == "stage_selection"
    assert out["model_id"] == "qwen-coder"
    assert out["provider_id"] == "local_openai"
    assert out["profile_available"] is True
    # Shadow selection observes only; it must not claim to change live routing.
    assert out["changes_production_routing"] is False


def test_unresolved_when_nothing_configured(tmp_path):
    svc = ForgeService(tmp_path, env={})
    out = svc.resolve_active_codegen_model()
    assert out["source"] == "unresolved"
    assert out["model_id"] == ""
    assert out["profile_available"] is False


def test_probe_live_discovers_running_local_model(tmp_path, monkeypatch):
    # Nothing configured, but the local server is up and advertises a model: probe_live discovers
    # it so identity attaches even before the model is registered/profiled in Forge.
    svc = ForgeService(tmp_path, env={"FORGE_LOCAL_BASE_URL": "http://127.0.0.1:8080"})

    def fake_get(url, timeout):
        assert url.endswith("/v1/models")
        return 200, json.dumps({"data": [{"id": "Qwen3.6-35B-A3B-UD-IQ4_XS.gguf"}]})

    monkeypatch.setattr(svc, "local_catalog", lambda **kw: svc.__class__.local_catalog(svc, http_get=fake_get))
    out = svc.resolve_active_codegen_model(probe_live=True)
    assert out["source"] == "live_local_probe"
    assert out["model_id"] == "Qwen3.6-35B-A3B-UD-IQ4_XS.gguf"
    assert out["provider_id"] == LOCAL_OPENAI_PROVIDER_ID


def test_probe_live_off_by_default(tmp_path):
    # Without probe_live, an unconfigured Forge stays unresolved (no network call, safe default).
    svc = ForgeService(tmp_path, env={"FORGE_LOCAL_BASE_URL": "http://127.0.0.1:8080"})
    out = svc.resolve_active_codegen_model()
    assert out["source"] == "unresolved"
