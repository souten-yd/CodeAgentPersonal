from pathlib import Path
from types import SimpleNamespace
import threading

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.jobs import JobSubmitRequest, normalize_lumen_job_mode
from app.server import create_app
from app.services.jobs import submit_job_service
import main


SERVICES_PATH = Path("app/services/jobs.py")


def test_job_submit_request_default_mode_is_chat():
    req = JobSubmitRequest(message="hello")
    assert req.mode == "chat"


@pytest.mark.parametrize("mode", [None, "", "chat", "lumen", "conversation"])
def test_lumen_modes_normalize_to_chat(mode):
    assert normalize_lumen_job_mode(mode) == "chat"


@pytest.mark.parametrize("mode", ["task", "agent_task", "legacy_task"])
def test_legacy_task_modes_are_rejected(mode):
    with pytest.raises(ValueError, match="legacy_task_mode_removed"):
        normalize_lumen_job_mode(mode)


def test_jobs_submit_rejects_legacy_task_mode_before_provider():
    app = create_app()
    called = []

    def provider(req):
        called.append(req)
        return {"job_id": "should-not-exist"}

    app.state.job_submit_provider = provider
    client = TestClient(app)
    response = client.post("/jobs/submit", json={"message": "hi", "mode": "task"})

    assert response.status_code == 410
    assert response.json()["error"] == "legacy_task_mode_removed"
    assert "job_id" not in response.json()
    assert called == []


def test_submit_job_service_rejects_legacy_task_without_job_or_thread():
    created = []
    started = []

    class FakeThread:
        def __init__(self, **kwargs):
            started.append({"constructed": kwargs})

        def start(self):
            started.append({"started": True})

    req = SimpleNamespace(project="default", message="hi", mode="task")

    with pytest.raises(HTTPException) as excinfo:
        submit_job_service(
            req,
            create_job=lambda project, message, mode: created.append((project, message, mode)) or "job-1",
            thread_factory=FakeThread,
            background_runner=lambda job_id, req: None,
            current_model_key="contract-model",
        )

    assert excinfo.value.status_code == 410
    assert excinfo.value.detail["error"] == "legacy_task_mode_removed"
    assert created == []
    assert started == []


def test_submit_job_service_normalizes_lumen_alias_before_creating_job():
    created = []
    started = []

    class FakeThread:
        def __init__(self, *, target, args, daemon):
            self.target = target
            self.args = args
            self.daemon = daemon

        def start(self):
            started.append({"args": self.args, "daemon": self.daemon})

    req = SimpleNamespace(project="default", message="hi", mode="lumen")
    result = submit_job_service(
        req,
        create_job=lambda project, message, mode: created.append((project, message, mode)) or "job-1",
        thread_factory=FakeThread,
        background_runner=lambda job_id, req: None,
        current_model_key="contract-model",
    )

    assert result["job_id"] == "job-1"
    assert req.mode == "chat"
    assert created == [("default", "hi", "chat")]
    assert started == [{"args": ("job-1", req), "daemon": True}]


def test_run_job_background_service_is_chat_only_and_legacy_strings_are_removed():
    text = SERVICES_PATH.read_text(encoding="utf-8")
    assert 'req.mode == "chat"' not in text
    assert "run_task_mode_stream" not in text
    assert "JSON形式で出力" not in text
    assert "options_prompt" not in text
    assert "approved_tasks" not in text


def test_run_job_background_service_calls_only_lumen_chat_executor():
    events = []
    statuses = []
    saved = []
    calls = []

    def execute(message, **kwargs):
        calls.append({"message": message, **kwargs})
        kwargs["on_event"]({"type": "llm_thinking", "step_num": 1})
        return {"status": "done", "output": "hello", "usage": {}, "steps": []}

    deps = SimpleNamespace(
        job_append_step=lambda project, job_id, seq, event_type, data: events.append((seq, event_type, data)),
        job_update_status=lambda project, job_id, status: statuses.append(status),
        job_log_append=lambda job_id, entry: None,
        execute_chat_with_optional_web_search=execute,
        save_session=lambda *args: saved.append(args),
        resolve_runtime_llm_url=lambda url: url or "http://llm",
        wait_threading=threading,
        job_wait_events={},
    )
    req = SimpleNamespace(
        project="default",
        message="hello",
        mode="chat",
        max_steps=99,
        search_enabled=None,
        search_policy="auto",
        search_budget={"max_queries": 99},
        llm_url="",
        chat_history=[],
    )

    main.run_job_background_service("job-1", req, deps)

    assert statuses[0] == "running"
    assert statuses[-1] == "done"
    assert calls[0]["max_steps"] == 20
    assert calls[0]["search_policy"] == "auto"
    assert calls[0]["search_budget"].max_queries == 5
    assert saved[0][3] == "chat"
