from pathlib import Path

from fastapi.testclient import TestClient

from app.api.jobs import default_job_submit_payload
from app.server import create_app
import main


JOBS_API_PATH = Path("app/api/jobs.py")
JOBS_SERVICE_PATH = Path("app/services/jobs.py")
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


def _submit_payload(message: str = "contract submit") -> dict:
    return {
        "message": message,
        "project": "default",
        "mode": "chat",
        "max_steps": 1,
        "search_enabled": False,
        "llm_url": "",
        "approved_tasks": None,
        "chat_history": [],
        "recommended_model": "",
        "auto_select_option": True,
        "auto_skill_generation": True,
    }


def test_create_app_post_jobs_submit_returns_safe_fallback_payload():
    app = create_app()
    client = TestClient(app)

    assert not hasattr(app.state, "job_submit_provider")

    response = client.post("/jobs/submit", json=_submit_payload())

    assert response.status_code == 200
    assert response.json() == default_job_submit_payload()
    assert response.json()["ok"] is False
    assert response.json()["status"] == "unavailable"
    assert response.json()["job_id"] is None
    assert "message" in response.json()


def test_create_app_submit_fallback_does_not_touch_runtime_side_effects(monkeypatch):
    app = create_app()
    client = TestClient(app)

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "jobs submit fallback must not start jobs, LLM, filesystem, ASR, or TTS"
        )

    monkeypatch.setattr("os.listdir", forbidden)
    monkeypatch.setattr("os.walk", forbidden)
    monkeypatch.setattr("os.path.exists", forbidden)
    monkeypatch.setattr("os.makedirs", forbidden)
    monkeypatch.setattr("builtins.open", forbidden)
    monkeypatch.setattr(main, "get_db", forbidden)
    monkeypatch.setattr(main, "job_create", forbidden)
    monkeypatch.setattr(main, "job_list", forbidden)
    monkeypatch.setattr(main, "job_get", forbidden)
    monkeypatch.setattr(main, "job_get_steps", forbidden)
    monkeypatch.setattr(main, "run_job_background", forbidden)
    monkeypatch.setattr(main, "call_llm_chat", forbidden, raising=False)
    monkeypatch.setattr(main, "execute_chat_with_optional_web_search", forbidden, raising=False)
    monkeypatch.setattr(main, "_model_manager", object(), raising=False)
    monkeypatch.setattr(main, "_asr_model", object(), raising=False)
    monkeypatch.setattr(main, "_tts_model", object(), raising=False)

    response = client.post("/jobs/submit", json=_submit_payload())

    assert response.status_code == 200
    assert response.json() == default_job_submit_payload()


def test_main_app_registers_callable_job_submit_provider():
    assert callable(main.app.state.job_submit_provider)
    assert main.app.state.job_submit_provider is main.job_submit_payload


def test_post_jobs_submit_route_is_owned_by_jobs_router():
    route = _single_route("/jobs/submit", "POST")

    assert route.endpoint.__module__ == "app.api.jobs"
    assert route.endpoint.__name__ == "submit_job_api"
    assert '@app.post("/jobs/submit")' not in MAIN_PATH.read_text(encoding="utf-8")


def test_jobs_service_does_not_import_main_and_jobs_router_does_not_inline_background_runtime():
    service_text = JOBS_SERVICE_PATH.read_text(encoding="utf-8")
    router_text = JOBS_API_PATH.read_text(encoding="utf-8")

    assert "import main" not in service_text
    assert "from main import" not in service_text
    assert "def run_job_background_service" not in router_text
    assert "run_job_background_service(" not in router_text


def test_main_provider_preserves_existing_queued_response_shape_without_running_background(
    monkeypatch,
):
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
    response = client.post("/jobs/submit", json=_submit_payload())

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
