from fastapi.testclient import TestClient

import main


def _endpoint_module(app, path: str) -> str:
    for route in app.routes:
        if getattr(route, "path", None) == path:
            return route.endpoint.__module__
    raise AssertionError(f"{path} route not found")


def test_main_app_system_usage_endpoint_contract():
    client = TestClient(main.app)

    response = client.get("/system/usage")
    body = response.json()

    assert _endpoint_module(main.app, "/system/usage") == "app.api.system"
    assert response.status_code == 200
    assert isinstance(body["cpu_percent"], (int, float))
    assert isinstance(body["ram_total_mb"], int)
    assert isinstance(body["ram_used_mb"], int)
    assert isinstance(body["gpu_backend"], str)
    assert isinstance(body["gpu_backend_selected"], str)
    assert isinstance(body["gpus"], list)
    assert isinstance(body["updated_at"], str)


def test_main_app_system_usage_debug_endpoint_contract():
    client = TestClient(main.app)

    response = client.get("/system/usage/debug")
    body = response.json()

    assert _endpoint_module(main.app, "/system/usage/debug") == "app.api.system"
    assert response.status_code == 200
    assert isinstance(body["gpu_backend_selected"], str)
    assert isinstance(body["gpu_backend"], str)
    assert isinstance(body["raw_parse_summary"], list)
    assert isinstance(body["parse_source"], str)
    assert isinstance(body["nvidia_smi_failure_reason"], str)
    assert isinstance(body["adopted_values"], dict)
    assert isinstance(body["final_usage"], dict)
    assert isinstance(body["final_usage"]["gpus"], list)


def test_main_app_system_env_endpoint_contract():
    client = TestClient(main.app)

    response = client.get("/system/env")
    body = response.json()

    assert response.status_code == 200
    assert isinstance(body["runpod"], bool)
    assert isinstance(body["os"], dict)
    assert isinstance(body["gpu"], dict)
    assert isinstance(body["style_bert_vits2_device"], str)


def test_main_app_system_summary_endpoint_contract():
    client = TestClient(main.app)

    response = client.get("/system/summary")
    body = response.json()

    assert _endpoint_module(main.app, "/system/summary") == "app.api.system"
    assert response.status_code == 200
    assert isinstance(body["health"], dict)
    assert isinstance(body["health"]["llm"], str)
    assert isinstance(body["health"]["sandbox"], str)
    assert isinstance(body["model"], dict)
    assert "status" in body["model"]
    assert "current_key" in body["model"]
    assert isinstance(body["usage"], dict)
    assert isinstance(body["usage"]["gpus"], list)


def test_main_app_settings_endpoint_adjacent_system_state_contract():
    client = TestClient(main.app)

    response = client.get("/settings")
    body = response.json()

    assert response.status_code == 200
    assert isinstance(body["llm_root_folder"], str)
    assert isinstance(body["gpu_static_backend"], str)
    assert isinstance(body["gpu_usage_backend"], str)
    assert isinstance(body["feature_mode"], str)
    assert isinstance(body["streaming_enabled"], str)
