"""TA14: runtime generation policy preview API."""
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


def test_preview_unbenchmarked_uses_safe_default(tmp_path):
    client = _client(tmp_path)
    body = client.post("/api/forge/atlas-generation-policy/preview",
                       json={"change_class": "medium"}).json()
    assert body["selection_mode"] == "unbenchmarked_default"
    assert body["profile_available"] is False
    assert body["fallback_recommendation"]["route"] == "patch_dsl"
    assert body["fallback_recommendation"]["production_routing_changed"] is False


def test_preview_optimal_routing_off_is_recorded(tmp_path):
    client = _client(tmp_path)
    body = client.post("/api/forge/atlas-generation-policy/preview",
                       json={"change_class": "medium", "optimal_routing": False}).json()
    assert body["optimal_routing_enabled"] is False
    assert body["route_fitness_applied"] is False
    assert body["selection_mode"] == "forge_optimal_routing_off"


def test_preview_critical_keeps_critical_gate(tmp_path):
    client = _client(tmp_path)
    body = client.post("/api/forge/atlas-generation-policy/preview",
                       json={"change_class": "critical"}).json()
    assert body["policy"]["route"] == "critical_gate"
    assert body["fallback_recommendation"]["route"] == "critical_gate"


def test_preview_invalid_change_class_is_400(tmp_path):
    client = _client(tmp_path)
    resp = client.post("/api/forge/atlas-generation-policy/preview",
                       json={"change_class": "not_a_class"})
    assert resp.status_code == 400


def test_preview_rejects_unknown_fields(tmp_path):
    client = _client(tmp_path)
    resp = client.post("/api/forge/atlas-generation-policy/preview",
                       json={"change_class": "medium", "surprise": 1})
    assert resp.status_code == 422
