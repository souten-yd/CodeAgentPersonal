from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.nexus import router
from app.nexus.jobs import create_job
from main import app as main_app


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


def test_nexus_jobs_latest_api_returns_fallback_payload():
    client = TestClient(_app())
    response = client.get("/nexus/jobs/latest?project=default")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["project"] == "default"
    assert payload["jobs"] == []
    assert payload["job"] is None
    assert payload["count"] == 0


def test_nexus_jobs_latest_api_uses_registered_provider():
    assert callable(getattr(main_app.state, "nexus_latest_jobs_provider", None))
    client = TestClient(main_app)
    create_job("research_provider_test", status="running", metadata={"project": "default", "is_research_job": True})
    response = client.get("/nexus/jobs/latest?project=default&limit=1&include_terminal=true")
    assert response.status_code == 200
    payload = response.json()
    assert payload["jobs"]
    assert payload["jobs"][0]["job_id"] == "research_provider_test"
