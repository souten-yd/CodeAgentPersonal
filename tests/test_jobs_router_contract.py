from fastapi.testclient import TestClient

from app.api.jobs import default_job_poll_payload, default_project_jobs_payload
from app.server import create_app
import main


def test_create_app_job_read_only_endpoints_return_fallback_payloads():
    client = TestClient(create_app())

    jobs = client.get("/projects/default/jobs")
    poll = client.get("/jobs/dummy/poll?project=default&after=-1")

    assert jobs.status_code == 200
    assert jobs.json() == default_project_jobs_payload()
    assert poll.status_code == 200
    assert poll.json() == default_job_poll_payload()


def test_create_app_job_fallbacks_do_not_touch_runtime_storage_or_execution(monkeypatch):
    app = create_app()
    client = TestClient(app)

    assert not hasattr(app.state, "project_jobs_provider")
    assert not hasattr(app.state, "job_poll_provider")

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "jobs router fallback must not touch filesystem, jobs, LLM, ASR, TTS, or execution"
        )

    monkeypatch.setattr("os.listdir", forbidden)
    monkeypatch.setattr("os.walk", forbidden)
    monkeypatch.setattr("os.path.exists", forbidden)
    monkeypatch.setattr("os.makedirs", forbidden)
    monkeypatch.setattr("builtins.open", forbidden)
    monkeypatch.setattr(main, "get_db", forbidden)
    monkeypatch.setattr(main, "job_list", forbidden)
    monkeypatch.setattr(main, "job_get", forbidden)
    monkeypatch.setattr(main, "job_get_steps", forbidden)
    monkeypatch.setattr(main, "run_job_background", forbidden)
    monkeypatch.setattr(main, "call_llm_chat", forbidden, raising=False)
    monkeypatch.setattr(main, "execute_chat_with_optional_web_search", forbidden, raising=False)
    monkeypatch.setattr(main, "_model_manager", object(), raising=False)
    monkeypatch.setattr(main, "_asr_model", object(), raising=False)
    monkeypatch.setattr(main, "_tts_model", object(), raising=False)

    assert client.get("/projects/default/jobs").json() == {"jobs": []}
    assert client.get("/jobs/dummy/poll?project=default&after=-1").json() == {
        "status": "done",
        "steps": [],
    }


def test_main_app_registers_job_read_only_providers():
    assert main.app.state.project_jobs_provider is main.project_jobs_payload
    assert main.app.state.job_poll_provider is main.job_poll_payload


def test_main_app_job_read_only_routes_use_provider_backed_existing_shapes(monkeypatch):
    monkeypatch.setattr(
        main.app.state,
        "project_jobs_provider",
        lambda project, limit=30: {
            "jobs": [
                {
                    "id": "job-1",
                    "message": project,
                    "mode": "chat",
                    "status": "done",
                    "created_at": "2026-05-09T00:00:00",
                    "updated_at": "2026-05-09T00:00:01",
                }
            ]
        },
        raising=False,
    )
    monkeypatch.setattr(
        main.app.state,
        "job_poll_provider",
        lambda job_id, project="default", after=-1: {
            "status": "running",
            "steps": [
                {
                    "seq": after + 1,
                    "type": "progress",
                    "data": {"job_id": job_id, "project": project},
                    "ts": "2026-05-09T00:00:01",
                }
            ],
        },
        raising=False,
    )

    client = TestClient(main.app)

    jobs = client.get("/projects/default/jobs?limit=1").json()
    assert set(jobs) == {"jobs"}
    assert jobs["jobs"][0]["id"] == "job-1"
    assert jobs["jobs"][0]["status"] == "done"

    poll = client.get("/jobs/job-1/poll?project=default&after=-1").json()
    assert set(poll) == {"status", "steps"}
    assert poll["status"] == "running"
    assert poll["steps"][0]["seq"] == 0
