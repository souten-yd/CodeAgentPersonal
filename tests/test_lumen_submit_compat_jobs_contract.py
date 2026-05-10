from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.server import create_app
from app.services.lumen_runtime import submit_lumen_job_service
import main


def _route(path: str, method: str):
    matches = [
        route
        for route in main.app.routes
        if getattr(route, "path", None) == path and method in getattr(route, "methods", set())
    ]
    assert len(matches) == 1
    return matches[0]


def test_jobs_submit_remains_and_lumen_submit_is_primary_router():
    assert _route("/jobs/submit", "POST").endpoint.__module__ == "app.api.jobs"
    assert _route("/lumen/submit", "POST").endpoint.__module__ == "app.api.lumen"


def test_jobs_and_lumen_submit_use_same_provider_service(monkeypatch):
    calls = []

    def provider(req):
        calls.append((req.mode, req.message))
        return {"job_id": f"job-{len(calls)}", "status": "queued", "model": "contract"}

    app = create_app()
    app.state.job_submit_provider = provider
    client = TestClient(app)

    assert client.post("/jobs/submit", json={"message": "compat"}).json()["status"] == "queued"
    assert client.post("/lumen/submit", json={"message": "primary"}).json()["status"] == "queued"
    assert calls == [("chat", "compat"), ("chat", "primary")]


def test_submit_service_mode_defaults_aliases_and_rejects_task_without_side_effects():
    created = []
    started = []

    class FakeThread:
        def __init__(self, *, target, args, daemon):
            self.args = args
            self.daemon = daemon

        def start(self):
            started.append({"args": self.args, "daemon": self.daemon})

    def create_job(project, message, mode):
        created.append((project, message, mode))
        return f"job-{len(created)}"

    default_req = SimpleNamespace(project="default", message="hello", mode=None)
    chat_result = submit_lumen_job_service(
        default_req,
        create_job=create_job,
        thread_factory=FakeThread,
        background_runner=lambda *_: None,
        current_model_key="model",
    )
    assert chat_result["status"] == "queued"
    assert default_req.mode == "chat"

    lumen_req = SimpleNamespace(project="default", message="hello", mode="lumen")
    submit_lumen_job_service(
        lumen_req,
        create_job=create_job,
        thread_factory=FakeThread,
        background_runner=lambda *_: None,
        current_model_key="model",
    )
    assert lumen_req.mode == "chat"
    assert created == [("default", "hello", "chat"), ("default", "hello", "chat")]
    assert len(started) == 2

    with pytest.raises(HTTPException) as excinfo:
        submit_lumen_job_service(
            SimpleNamespace(project="default", message="no", mode="task"),
            create_job=create_job,
            thread_factory=FakeThread,
            background_runner=lambda *_: None,
            current_model_key="model",
        )
    assert excinfo.value.status_code == 410
    assert excinfo.value.detail["error"] == "legacy_task_mode_removed"
    assert len(created) == 2
    assert len(started) == 2


def test_lumen_submit_rejects_task_before_provider():
    app = create_app()
    calls = []
    app.state.job_submit_provider = lambda req: calls.append(req) or {"job_id": "bad"}
    response = TestClient(app).post("/lumen/submit", json={"message": "hi", "mode": "task"})
    assert response.status_code == 410
    assert response.json()["error"] == "legacy_task_mode_removed"
    assert calls == []
