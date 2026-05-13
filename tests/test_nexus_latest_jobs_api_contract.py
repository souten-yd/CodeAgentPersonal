from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.nexus import router


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


def test_nexus_jobs_latest_api_returns_fallback_payload():
    client = TestClient(_app())
    response = client.get("/nexus/jobs/latest?project=default")
    assert response.status_code == 200
    payload = response.json()
    assert payload["project"] == "default"
    assert payload["jobs"] == []
    assert payload["job"] is None
