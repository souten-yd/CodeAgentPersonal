from fastapi.testclient import TestClient

from app.api.projects import (
    default_project_files_payload,
    default_project_history_payload,
    default_projects_payload,
)
from app.server import create_app
import main


def test_create_app_project_read_only_endpoints_return_fallback_payloads():
    client = TestClient(create_app())

    projects = client.get("/projects")
    history = client.get("/projects/default/history")
    files = client.get("/projects/default/files")

    assert projects.status_code == 200
    assert projects.json() == default_projects_payload()
    assert history.status_code == 200
    assert history.json() == default_project_history_payload()
    assert files.status_code == 200
    assert files.json() == default_project_files_payload("default")


def test_create_app_project_fallbacks_do_not_require_runtime_or_storage_providers(monkeypatch):
    app = create_app()
    client = TestClient(app)

    assert not hasattr(app.state, "projects_list_provider")
    assert not hasattr(app.state, "project_history_provider")
    assert not hasattr(app.state, "project_files_provider")

    def forbidden(*args, **kwargs):
        raise AssertionError("project router fallback must not touch filesystem, jobs, or runtime")

    monkeypatch.setattr("os.listdir", forbidden)
    monkeypatch.setattr("os.walk", forbidden)
    monkeypatch.setattr("os.path.exists", forbidden)
    monkeypatch.setattr("os.makedirs", forbidden)
    monkeypatch.setattr(main, "get_db", forbidden)
    monkeypatch.setattr(main, "jobs", object(), raising=False)
    monkeypatch.setattr(main, "_model_manager", object(), raising=False)

    assert client.get("/projects").json() == {"projects": []}
    assert client.get("/projects/default/history").json() == {"sessions": []}
    assert client.get("/projects/default/files").json() == {
        "project": "default",
        "files": [],
    }


def test_main_app_project_routes_use_provider_backed_existing_shapes(monkeypatch):
    monkeypatch.setattr(
        main.app.state,
        "projects_list_provider",
        lambda: {
            "projects": [
                {"name": "default", "files": ["README.md"], "file_count": 1}
            ]
        },
        raising=False,
    )
    monkeypatch.setattr(
        main.app.state,
        "project_history_provider",
        lambda project: {
            "sessions": [
                {
                    "id": 1,
                    "timestamp": "2026-05-09T00:00:00Z",
                    "mode": "chat",
                    "message": project,
                    "status": "done",
                    "result": {"ok": True},
                }
            ]
        },
        raising=False,
    )
    monkeypatch.setattr(
        main.app.state,
        "project_files_provider",
        lambda project: {"project": project, "files": ["README.md"]},
        raising=False,
    )

    client = TestClient(main.app)

    projects = client.get("/projects").json()
    assert set(projects) == {"projects"}
    assert projects["projects"] == [
        {"name": "default", "files": ["README.md"], "file_count": 1}
    ]

    history = client.get("/projects/default/history").json()
    assert set(history) == {"sessions"}
    assert history["sessions"][0]["message"] == "default"

    files = client.get("/projects/default/files").json()
    assert files == {"project": "default", "files": ["README.md"]}
