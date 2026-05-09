from pathlib import Path

from fastapi.testclient import TestClient

from app.services import jobs as jobs_service
import main


SERVICE_PATH = Path("app/services/jobs.py")
MAIN_PATH = Path("main.py")


def _routes_for(path: str, method: str) -> list:
    return [
        route
        for route in main.app.routes
        if getattr(route, "path", None) == path
        and method.upper() in getattr(route, "methods", set())
    ]


def _single_route(path: str, method: str):
    routes = _routes_for(path, method)
    assert len(routes) == 1
    return routes[0]


def test_jobs_service_module_exists_and_exports_execution_boundaries():
    assert SERVICE_PATH.exists()
    assert callable(jobs_service.submit_job_service)
    assert callable(jobs_service.run_job_background_service)
    assert callable(jobs_service.append_job_event)
    assert callable(jobs_service.finalize_job)
    assert callable(jobs_service.fail_job)


def test_jobs_service_does_not_import_main_or_own_http_routes():
    text = SERVICE_PATH.read_text(encoding="utf-8")
    forbidden_imports = ["import main", "from main import"]
    for forbidden in forbidden_imports:
        assert forbidden not in text

    forbidden_route_markers = ["@app.", "APIRouter", "@router."]
    for forbidden in forbidden_route_markers:
        assert forbidden not in text


def test_submit_route_moves_to_jobs_router_and_main_keeps_service_provider():
    route = _single_route("/jobs/submit", "POST")
    assert route.endpoint.__module__ == "app.api.jobs"
    assert route.endpoint.__name__ == "submit_job_api"

    text = MAIN_PATH.read_text(encoding="utf-8")
    assert '@app.post("/jobs/submit")' not in text
    assert "def job_submit_payload(" in text
    assert "app.state.job_submit_provider = job_submit_payload" in text
    assert "submit_job_service(" in text
    assert "run_job_background_service(" in text


def test_jobs_read_only_routes_stay_jobs_router_owned():
    poll = _single_route("/jobs/{job_id}/poll", "GET")
    project_jobs = _single_route("/projects/{project}/jobs", "GET")

    assert poll.endpoint.__module__ == "app.api.jobs"
    assert poll.endpoint.__name__ == "get_job_poll_api"
    assert project_jobs.endpoint.__module__ == "app.api.jobs"
    assert project_jobs.endpoint.__name__ == "get_project_jobs_api"


def test_post_jobs_submit_preserves_response_shape_without_running_background(monkeypatch):
    started = []

    class FakeThread:
        def __init__(self, *, target, args, daemon):
            self.target = target
            self.args = args
            self.daemon = daemon

        def start(self):
            started.append({"target": self.target, "args": self.args, "daemon": self.daemon})

    monkeypatch.setattr(main, "job_create", lambda project, message, mode: "job-contract-1")
    monkeypatch.setattr(main._job_threading, "Thread", FakeThread)
    monkeypatch.setattr(main._model_manager, "current_key", "contract-model", raising=False)

    client = TestClient(main.app)
    response = client.post(
        "/jobs/submit",
        json={
            "message": "contract submit",
            "project": "default",
            "mode": "chat",
            "max_steps": 1,
            "search_enabled": False,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "job_id": "job-contract-1",
        "status": "queued",
        "model": "contract-model",
    }
    assert len(started) == 1
    assert started[0]["target"] is main.run_job_background
    assert started[0]["args"][0] == "job-contract-1"
    assert started[0]["daemon"] is True
