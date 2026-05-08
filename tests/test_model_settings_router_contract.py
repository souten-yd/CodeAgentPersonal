from fastapi.testclient import TestClient

from app.api.model_settings import default_model_orchestration_payload
from app.server import create_app
import main


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
