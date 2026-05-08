from fastapi.testclient import TestClient

from app.api.model_settings import (
    default_model_db_list_payload,
    default_model_db_status_payload,
    default_model_manager_status_payload,
    default_model_orchestration_payload,
    default_model_roles_payload,
)
from app.server import create_app
import main


def test_create_app_model_manager_status_returns_default_payload():
    client = TestClient(create_app())

    response = client.get("/model/status")

    assert response.status_code == 200
    assert response.json() == default_model_manager_status_payload()


def test_main_app_model_manager_status_returns_provider_payload(monkeypatch):
    expected = {
        "status": "ready",
        "current_key": "coder-a",
        "catalog": {"coder-a": {"model_key": "coder-a"}},
        "extra": {"preserved": True},
    }

    class FakeModelManager:
        def status_dict(self):
            return expected

    monkeypatch.setattr(main, "_model_manager", FakeModelManager())

    response = TestClient(main.app).get("/model/status")

    assert response.status_code == 200
    assert response.json() == expected


def test_create_app_model_orchestration_returns_default_payload():
    client = TestClient(create_app())

    response = client.get("/models/orchestration")

    assert response.status_code == 200
    assert response.json() == default_model_orchestration_payload()


def test_main_app_model_orchestration_returns_provider_payload(monkeypatch):
    monkeypatch.setattr(
        main,
        "settings_get",
        lambda key: {
            "feature_mode": "model_orchestration",
            "orchestration_policy": "ladder_fail_and_quality",
            "quality_check_enabled": "true",
            "coder_primary": "coder-a",
            "coder_secondary": "coder-b",
            "coder_tertiary": "",
        }.get(key, ""),
    )
    monkeypatch.setattr(
        main,
        "get_runtime_model_catalog",
        lambda include_disabled=False: {
            "coder-a": {"model_key": "coder-a"},
            "coder-b": {"model_key": "coder-b"},
        },
    )
    monkeypatch.setattr(main, "get_coder_ladder_keys", lambda catalog: ["coder-a", "coder-b"])
    monkeypatch.setattr(
        main,
        "model_db_list",
        lambda: [
            {
                "model_key": "coder-a",
                "name": "Coder A",
                "enabled": 1,
                "tok_per_sec": 12.5,
                "benchmark_profiles": "",
            }
        ],
    )

    response = TestClient(main.app).get("/models/orchestration")
    body = response.json()

    assert response.status_code == 200
    assert body == {
        "feature_mode": "model_orchestration",
        "policy": "ladder_fail_and_quality",
        "quality_check_enabled": True,
        "coder_primary": "coder-a",
        "coder_secondary": "coder-b",
        "coder_tertiary": "",
        "resolved_ladder": ["coder-a", "coder-b"],
        "models": [
            {
                "model_key": "coder-a",
                "name": "Coder A",
                "enabled": 1,
                "tok_per_sec": 12.5,
            }
        ],
    }


def test_create_app_model_db_list_returns_default_payload():
    client = TestClient(create_app())

    response = client.get("/models/db")

    assert response.status_code == 200
    assert response.json() == default_model_db_list_payload()


def test_main_app_model_db_list_returns_provider_payload(monkeypatch):
    monkeypatch.setattr(
        main,
        "model_db_list",
        lambda: [
            {
                "id": "m1",
                "model_key": "coder-a",
                "name": "Coder A",
                "ctx_size": "raw-ctx",
                "tok_per_sec": 12.5,
            },
            {
                "id": "m2",
                "model_key": "coder-b",
                "name": "Coder B",
                "ctx_size": None,
                "tok_per_sec": -1,
            },
        ],
    )
    monkeypatch.setattr(
        main,
        "_resolve_ctx_size",
        lambda value=None: 4096 if value == "raw-ctx" else 2048,
    )

    response = TestClient(main.app).get("/models/db")
    body = response.json()

    assert response.status_code == 200
    assert body["count"] == 2
    assert len(body["models"]) == 2
    assert body["models"][0] == {
        "id": "m1",
        "model_key": "coder-a",
        "name": "Coder A",
        "ctx_size": 4096,
        "tok_per_sec": 12.5,
    }
    assert body["models"][1]["ctx_size"] == 2048


def test_create_app_model_db_status_returns_default_payload():
    client = TestClient(create_app())

    response = client.get("/models/db/status")

    assert response.status_code == 200
    assert response.json() == default_model_db_status_payload()


def test_main_app_model_db_status_returns_provider_payload(monkeypatch):
    monkeypatch.setattr(main, "model_db_exists", lambda: True)
    monkeypatch.setattr(
        main,
        "model_db_list",
        lambda: [
            {"id": "m1", "tok_per_sec": 12.5, "is_vlm": 0},
            {"id": "m2", "tok_per_sec": 0, "is_vlm": 1},
            {"id": "m3", "tok_per_sec": -1, "is_vlm": 0},
        ],
    )
    monkeypatch.setattr(main, "MODEL_DB_PATH", "/tmp/test-models.db")

    response = TestClient(main.app).get("/models/db/status")
    body = response.json()

    assert response.status_code == 200
    assert body == {
        "db_exists": True,
        "has_models": True,
        "total": 3,
        "benchmarked": 1,
        "has_vlm": True,
        "db_path": "/tmp/test-models.db",
    }


def test_create_app_model_roles_returns_default_payload():
    client = TestClient(create_app())

    response = client.get("/models/roles")

    assert response.status_code == 200
    assert response.json() == default_model_roles_payload()


def test_main_app_model_roles_returns_provider_payload(monkeypatch):
    monkeypatch.setattr(main, "MODEL_ROLE_OPTIONS", ("plan", "code", "chat"))
    monkeypatch.setattr(
        main,
        "settings_get",
        lambda key: "coder-a" if key == "role_model_plan" else "",
    )
    monkeypatch.setattr(
        main,
        "get_runtime_model_catalog",
        lambda include_disabled=False: {
            "coder-a": {"model_key": "coder-a"},
            "coder-b": {"model_key": "coder-b"},
        },
    )
    monkeypatch.setattr(
        main,
        "get_runtime_task_model_map",
        lambda catalog, include_disabled=False: {
            "plan": "coder-a",
            "code": "coder-b",
            "chat": "coder-a",
        },
    )
    monkeypatch.setattr(
        main,
        "_get_auto_role_model_map",
        lambda catalog: {"code": "coder-b"},
    )
    monkeypatch.setattr(
        main,
        "model_db_list",
        lambda: [
            {
                "id": "m1",
                "model_key": "coder-a",
                "name": "Coder A",
                "enabled": 1,
                "vlm_enabled": 1,
                "is_vlm": 0,
                "ctx_size": "4096",
                "auto_roles": "plan,chat",
            }
        ],
    )
    monkeypatch.setattr(main, "_resolve_ctx_size", lambda value=None: 4096)

    response = TestClient(main.app).get("/models/roles")
    body = response.json()

    assert response.status_code == 200
    assert body == {
        "roles": ["plan", "code", "chat"],
        "planner_key": "coder-a",
        "assignments": {
            "plan": {"model_key": "coder-a", "source": "explicit"},
            "code": {"model_key": "coder-b", "source": "auto"},
            "chat": {"model_key": "coder-a", "source": "planner_fallback"},
        },
        "models": [
            {
                "id": "m1",
                "model_key": "coder-a",
                "name": "Coder A",
                "enabled": 1,
                "vlm_enabled": 1,
                "is_vlm": 0,
                "ctx_size": 4096,
                "auto_roles": ["plan", "chat"],
            }
        ],
    }
