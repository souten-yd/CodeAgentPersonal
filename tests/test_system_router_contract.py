from fastapi.testclient import TestClient

from app.api.system import SYSTEM_READINESS_DEFAULT_PAYLOAD
from app.server import create_app
import main


def test_create_app_system_readiness_response_contract():
    client = TestClient(create_app())

    response = client.get("/system/readiness")

    assert response.status_code == 200
    assert response.json() == SYSTEM_READINESS_DEFAULT_PAYLOAD


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
