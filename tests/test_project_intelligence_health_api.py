"""PIR-2 read-only health API tests."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.atlas_project_intelligence import router
from agent.project_intelligence.rollout import ENV_ENABLED, RolloutConfig
from agent.project_intelligence.service_registry import (
    close_project_intelligence_service,
    register_project_intelligence_service,
)


def test_health_api_reports_registered_service_without_private_rows(tmp_path) -> None:
    app = FastAPI()
    app.include_router(router)
    register_project_intelligence_service(
        app,
        ca_data_dir=tmp_path,
        rollout=RolloutConfig.from_env({ENV_ENABLED: "1"}),
    )
    try:
        response = TestClient(app).get("/api/atlas/project-intelligence/health")
    finally:
        close_project_intelligence_service(app)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["rollout"]["mode"] == "active"
    assert payload["preflight"]["implementation_classes"]["digital_twin"] == "DigitalTwinModuleImpl"
    assert "rows" not in str(payload).lower()


def test_health_api_is_safe_when_service_unregistered(tmp_path) -> None:
    app = FastAPI()
    app.state.atlas_ca_data_dir = str(tmp_path)
    app.include_router(router)
    response = TestClient(app).get("/api/atlas/project-intelligence/health")
    assert response.status_code == 200
    assert response.json()["status"] == "unregistered"

