import sys

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
    expected = {
        "db_exists": True,
        "has_models": True,
        "total": 3,
        "benchmarked": 1,
        "has_vlm": True,
        "db_path": "/tmp/test-models.db",
    }
    for key, value in expected.items():
        assert body[key] == value


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


def test_model_status_exposes_gpu_validation_failed(monkeypatch):
    class FakeModelManager:
        def status_dict(self):
            return {
                "status": "ready",
                "current_key": "coder-a",
                "catalog": {},
                "last_model_load_status": "error",
                "last_model_load_error": "GPU validation failed: cuda init failed; no usable GPU found",
                "gpu_validation_status": "fail",
                "last_gpu_validation_status": "fail",
                "gpu_validation_reason": "cuda init failed; no usable GPU found",
                "last_gpu_validation_reason": "cuda init failed; no usable GPU found",
                "gpu_validation_path": "explicit_cuda_failure",
                "last_gpu_validation_path": "explicit_cuda_failure",
                "cuda_init_failed": True,
                "no_usable_gpu": True,
                "llama_log_parser_stale_suspected": False,
                "llama_readiness_signals": {"process_signal": {"alive": False}},
            }

    monkeypatch.setattr(main, "_model_manager", FakeModelManager())

    response = TestClient(main.app).get("/model/status")

    assert response.status_code == 200
    body = response.json()
    assert body["gpu_validation_status"] == "fail"
    assert body["last_model_load_status"] == "error"
    assert body["cuda_init_failed"] is True
    assert body["no_usable_gpu"] is True


def _gpu_failed_model_manager_from_parsed_log():
    manager = main.ModelManager.__new__(main.ModelManager)
    manager._status = "ready"
    manager.current_key = "coder-a"
    manager._switch_eta = 0
    manager._last_start_cmd = "llama-server --model coder-a.gguf -ngl 99"
    manager.last_model_load_status = "loading"
    manager.last_model_load_error = None
    manager.last_gpu_validation_status = "pending"
    manager.last_gpu_validation_reason = None
    manager.last_gpu_validation_path = None
    manager.last_cuda_init_failed = False
    manager.last_no_usable_gpu = False
    manager._last_ngl_search_debug = {}
    manager._last_llama_gpu_log = {
        "gpu_validation_status": "fail",
        "gpu_validation_reason": "cuda init failed; no usable GPU found",
        "gpu_validation_path": "explicit_cuda_failure",
        "cuda_init_failed": True,
        "no_usable_gpu": True,
        "llama_log_parser_stale_suspected": False,
        "llama_readiness_signals": {"process_signal": {"alive": False}},
    }
    manager._sync_current_model = lambda: None
    manager._catalog = lambda: {
        "coder-a": {
            "name": "Coder A",
            "description": "Test model",
            "vram_gb": 8,
            "load_sec": 1,
            "path": "/models/coder-a.gguf",
        }
    }
    return manager


def test_model_status_provider_exposes_gpu_validation_failed_from_parsed_log(monkeypatch):
    monkeypatch.setattr(main, "_model_manager", _gpu_failed_model_manager_from_parsed_log())

    response = TestClient(main.app).get("/model/status")

    assert response.status_code == 200
    body = response.json()
    assert body["last_model_load_status"] == "error"
    assert body["gpu_validation_status"] == "fail"
    assert body["last_gpu_validation_status"] == "fail"
    assert body["cuda_init_failed"] is True
    assert body["no_usable_gpu"] is True
    assert body["gpu_validation_reason"] == "cuda init failed; no usable GPU found"
    assert body["last_start_cmd"] == "llama-server --model coder-a.gguf -ngl 99"


def test_llm_props_exposes_gpu_validation_failed_without_torch_probe(monkeypatch):
    class RaisingCuda:
        calls = 0

        @staticmethod
        def is_available():
            RaisingCuda.calls += 1
            raise AssertionError("torch.cuda.is_available must not be called by /llm/props")

    class FakeTorch:
        cuda = RaisingCuda

    monkeypatch.setitem(sys.modules, "torch", FakeTorch)
    monkeypatch.setattr(main, "_model_manager", _gpu_failed_model_manager_from_parsed_log())

    response = TestClient(main.app).get("/llm/props")

    assert response.status_code == 200
    body = response.json()
    assert RaisingCuda.calls == 0
    assert body["last_model_load_status"] == "error"
    assert body["gpu_validation_status"] == "fail"
    assert body["cuda_init_failed"] is True
    assert body["no_usable_gpu"] is True
