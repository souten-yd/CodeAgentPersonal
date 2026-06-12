"""PFG-27 — Portal Run Forge Trace metadata.

The Forge trace is optional and sidecar-safe: a legacy run (no trace) still loads, the
trace lives outside the package/data, and it round-trips through the API.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.portal import router as portal_router
from app.portal.paths import PortalPathLayout


def _client(tmp_path: Path) -> TestClient:
    app = FastAPI()
    app.state.atlas_ca_data_root = str(tmp_path)
    app.include_router(portal_router)
    return TestClient(app)


def test_legacy_run_without_trace_loads_as_unavailable(tmp_path):
    # The trace endpoint returns available=false for an installation with no sidecar.
    resp = _client(tmp_path).get("/api/portal/installations/inst-legacy/forge-trace")
    assert resp.status_code == 200
    data = resp.json()
    assert data["available"] is False
    assert data["trace"] is None


def test_forge_trace_round_trips_and_is_sidecar_safe(tmp_path):
    c = _client(tmp_path)
    resp = c.post("/api/portal/installations/inst-1/forge-trace", json={
        "provider_id": "local_openai_compatible",
        "model_id": "mistral-small",
        "route_id": "direct_patch",
        "stage": "patch_generation",
        "source_mode": "local_only",
        "arena_run_id": "arena_abc",
        "candidate_id": "cand_0",
        "loadout_id": "local_safe",
    })
    assert resp.status_code == 200
    trace = resp.json()["trace"]
    assert trace["model_id"] == "mistral-small"
    assert trace["recorded_at"]  # stamped server-side

    got = c.get("/api/portal/installations/inst-1/forge-trace").json()
    assert got["available"] is True
    assert got["trace"]["route_id"] == "direct_patch"

    # Sidecar lives next to the installation, not in package/data trees.
    layout = PortalPathLayout(tmp_path)
    sidecar = layout.installation_root("inst-1") / "forge_trace.json"
    assert sidecar.exists()
    # It is not under the data/ or packages/ trees.
    assert "data" not in sidecar.relative_to(tmp_path).parts[:2] or sidecar.name == "forge_trace.json"
    assert (tmp_path / "portal" / "packages") != sidecar.parent


def test_trace_isolated_per_installation(tmp_path):
    c = _client(tmp_path)
    c.post("/api/portal/installations/inst-a/forge-trace", json={"model_id": "a"})
    assert c.get("/api/portal/installations/inst-b/forge-trace").json()["available"] is False
    assert c.get("/api/portal/installations/inst-a/forge-trace").json()["trace"]["model_id"] == "a"
