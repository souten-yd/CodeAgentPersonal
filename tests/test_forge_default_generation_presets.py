"""TA15: default generation routing presets."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.model_forge.default_generation_presets import (
    DEFAULT_GENERATION_PRESETS,
    UNSAFE_MICRO_ROUTES_FOR_LARGE,
    validate_presets_against_route_matrix,
)
from app.api.forge import router


def _client(tmp_path: Path) -> TestClient:
    app = FastAPI()
    app.state.atlas_ca_data_root = str(tmp_path)
    app.include_router(router)
    return TestClient(app)


def test_presets_do_not_contradict_route_matrix():
    assert validate_presets_against_route_matrix() == []


def test_critical_preset_uses_critical_gate():
    assert DEFAULT_GENERATION_PRESETS["unbenchmarked_safe"]["critical"]["route"] == "critical_gate"


def test_large_and_critical_avoid_unsafe_micro_routes():
    safe = DEFAULT_GENERATION_PRESETS["unbenchmarked_safe"]
    for class_name in ("large", "critical"):
        assert safe[class_name]["route"] not in UNSAFE_MICRO_ROUTES_FOR_LARGE


def test_every_change_class_has_a_preset():
    safe = DEFAULT_GENERATION_PRESETS["unbenchmarked_safe"]
    for class_name in ("trivial", "micro", "small", "medium", "large", "critical", "greenfield"):
        assert class_name in safe
        assert {"route", "method", "injection"} <= set(safe[class_name])


def test_default_presets_api(tmp_path):
    body = _client(tmp_path).get("/api/forge/atlas-generation-policy/default-presets").json()
    assert body["route_matrix_consistent"] is True
    assert body["violations"] == []
    assert body["presets"]["unbenchmarked_safe"]["medium"]["route"] == "patch_dsl"
    assert "optimal_routing_off" in body
