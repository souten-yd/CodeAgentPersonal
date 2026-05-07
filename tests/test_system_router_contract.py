from fastapi.testclient import TestClient

from app.api.system import (
    SYSTEM_READINESS_DEFAULT_PAYLOAD,
    default_system_usage_debug_unavailable_payload,
    default_system_usage_unavailable_payload,
)
from app.server import create_app
import main


def assert_system_env_response_contract(body):
    assert "runpod" in body
    assert "os" in body
    assert "gpu" in body
    assert "style_bert_vits2_device" in body
    assert isinstance(body["runpod"], bool)
    assert isinstance(body["os"], dict)
    assert isinstance(body["gpu"], dict)
    assert isinstance(body["style_bert_vits2_device"], str)


def test_default_system_usage_unavailable_payload_has_representative_contract_keys():
    payload = default_system_usage_unavailable_payload()

    assert isinstance(payload["cpu_percent"], (int, float))
    assert isinstance(payload["ram_total_mb"], int)
    assert isinstance(payload["ram_used_mb"], int)
    assert payload["gpu_backend"] == "unavailable"
    assert payload["gpu_backend_selected"] == "unavailable"
    assert payload["gpus"] == []
    assert payload["updated_at"] == ""


def test_default_system_usage_debug_unavailable_payload_has_representative_contract_keys():
    payload = default_system_usage_debug_unavailable_payload()

    assert payload["gpu_backend_selected"] == "unavailable"
    assert payload["gpu_backend"] == "unavailable"
    assert payload["raw_parse_summary"] == []
    assert payload["parse_source"] == "unavailable"
    assert payload["nvidia_smi_failure_reason"] == ""
    assert payload["adopted_values"] == {}
    assert isinstance(payload["final_usage"], dict)
    assert payload["final_usage"]["gpus"] == []


def test_create_app_system_readiness_response_contract():
    client = TestClient(create_app())

    response = client.get("/system/readiness")

    assert response.status_code == 200
    assert response.json() == SYSTEM_READINESS_DEFAULT_PAYLOAD


def test_create_app_system_usage_response_contract():
    client = TestClient(create_app())

    response = client.get("/system/usage")

    assert response.status_code == 200
    assert response.json() == default_system_usage_unavailable_payload()


def test_create_app_system_usage_debug_response_contract():
    client = TestClient(create_app())

    response = client.get("/system/usage/debug")

    assert response.status_code == 200
    assert response.json() == default_system_usage_debug_unavailable_payload()


def test_main_app_system_usage_response_contract():
    client = TestClient(main.app)

    response = client.get("/system/usage")
    body = response.json()

    assert response.status_code == 200
    assert isinstance(body["cpu_percent"], (int, float))
    assert isinstance(body["ram_total_mb"], int)
    assert isinstance(body["ram_used_mb"], int)
    assert isinstance(body["gpu_backend"], str)
    assert isinstance(body["gpu_backend_selected"], str)
    assert isinstance(body["gpus"], list)
    assert isinstance(body["updated_at"], str)


def test_main_app_system_usage_debug_response_contract():
    client = TestClient(main.app)

    response = client.get("/system/usage/debug")
    body = response.json()

    assert response.status_code == 200
    assert isinstance(body["gpu_backend_selected"], str)
    assert isinstance(body["gpu_backend"], str)
    assert isinstance(body["raw_parse_summary"], list)
    assert isinstance(body["parse_source"], str)
    assert isinstance(body["nvidia_smi_failure_reason"], str)
    assert isinstance(body["adopted_values"], dict)
    assert isinstance(body["final_usage"], dict)
    assert isinstance(body["final_usage"]["gpus"], list)


def test_main_app_system_readiness_response_contract():
    client = TestClient(main.app)

    response = client.get("/system/readiness")
    body = response.json()

    assert response.status_code == 200
    assert set(body) == set(SYSTEM_READINESS_DEFAULT_PAYLOAD)
    assert body["fastapi"] == "ready"
    assert isinstance(body["model_db_exists"], bool)
    assert isinstance(body["model_db_status_available"], bool)
    assert isinstance(body["model_db_status"], dict)
    assert isinstance(body["llm_autoload_eligible"], bool)
    assert isinstance(body["autoload_reason"], str)
    assert isinstance(body["llm_running"], bool)


def test_create_app_system_env_response_contract():
    client = TestClient(create_app())

    response = client.get("/system/env")
    body = response.json()

    assert response.status_code == 200
    assert_system_env_response_contract(body)


def test_main_app_system_env_response_contract():
    client = TestClient(main.app)

    response = client.get("/system/env")
    body = response.json()

    assert response.status_code == 200
    assert_system_env_response_contract(body)
