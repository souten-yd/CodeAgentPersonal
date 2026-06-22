"""Forge tab bootstrap: one aggregate call instead of ~11 separate GETs."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.forge import router


def _client(tmp_path: Path) -> TestClient:
    app = FastAPI()
    app.state.atlas_ca_data_root = str(tmp_path)
    app.include_router(router)
    return TestClient(app)


def test_bootstrap_returns_all_init_sections(tmp_path):
    body = _client(tmp_path).get("/api/forge/bootstrap").json()
    for key in ("status", "providers", "settings", "profiles", "leaderboard", "presets",
                "stage_policy", "route_policy", "loadouts", "twin_settings", "twin_profiles"):
        assert key in body, key
    # External/lazy data is intentionally NOT bundled (kept fast / fetched in parallel by the UI).
    assert "openrouter_catalog" not in body
    assert "local_models" not in body
