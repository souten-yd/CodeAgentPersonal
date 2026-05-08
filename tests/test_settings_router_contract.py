from fastapi.testclient import TestClient

import main
from app.server import create_app


def _assert_representative_defaults_payload(body: dict) -> None:
    assert isinstance(body, dict)
    assert str(body["ctx_size"]).isdigit()
    assert body["search_enabled"] in {"true", "false"}
    assert body["streaming_enabled"] in {"true", "false"}
    assert body["feature_mode"] in {"model_orchestration", "ensemble"}


def test_create_app_settings_returns_conservative_fallback_payload():
    client = TestClient(create_app())

    response = client.get("/settings")
    body = response.json()

    assert response.status_code == 200
    assert isinstance(body, dict)
    assert isinstance(body["llm_root_folder"], str)
    assert body["search_enabled"] in {"true", "false"}
    assert body["streaming_enabled"] in {"true", "false"}
    assert str(body["ctx_size"]).isdigit()
    assert body["feature_mode"] in {"model_orchestration", "ensemble"}
    assert body["ensemble_execution_mode"] in {"parallel", "serial"}


def test_main_app_settings_uses_existing_full_settings_provider():
    client = TestClient(main.app)

    response = client.get("/settings")
    body = response.json()

    assert response.status_code == 200
    assert isinstance(body, dict)
    assert isinstance(body["llm_root_folder"], str)
    assert body["search_enabled"] in {"true", "false"}
    assert body["streaming_enabled"] in {"true", "false"}
    assert str(body["ctx_size"]).isdigit()
    assert body["feature_mode"] in {"model_orchestration", "ensemble"}
    assert body["ensemble_execution_mode"] in {"parallel", "serial"}


def test_create_app_setting_by_key_returns_conservative_fallback_payload():
    client = TestClient(create_app())

    response = client.get("/settings/ctx_size")
    body = response.json()

    assert response.status_code == 200
    assert body["key"] == "ctx_size"
    assert str(body["value"]).isdigit()


def test_main_app_setting_by_key_uses_existing_key_value_provider():
    client = TestClient(main.app)

    response = client.get("/settings/ctx_size")
    body = response.json()

    assert response.status_code == 200
    assert body["key"] == "ctx_size"
    assert str(body["value"]).isdigit()


def test_create_app_settings_defaults_alias_returns_conservative_fallback_payload():
    client = TestClient(create_app())

    response = client.get("/settings-defaults")
    body = response.json()

    assert response.status_code == 200
    _assert_representative_defaults_payload(body)


def test_main_app_settings_defaults_alias_uses_existing_defaults_provider():
    client = TestClient(main.app)

    response = client.get("/settings-defaults")
    body = response.json()

    assert response.status_code == 200
    _assert_representative_defaults_payload(body)


def test_create_app_setting_write_returns_conservative_fallback_without_db_write():
    client = TestClient(create_app())

    response = client.put("/settings/test_key", json={"value": "factory-value"})
    body = response.json()

    assert response.status_code == 200
    assert body == {"ok": True, "key": "test_key", "value": "factory-value"}


def test_main_app_setting_write_uses_existing_single_key_provider(monkeypatch):
    calls = []
    monkeypatch.setattr(
        main,
        "settings_set",
        lambda key, value: calls.append((key, value)),
    )
    client = TestClient(main.app)

    response = client.put("/settings/router_contract_safe_key", json={"value": "safe-value"})
    body = response.json()

    assert response.status_code == 200
    assert body == {"ok": True, "key": "router_contract_safe_key", "value": "safe-value"}
    assert calls == [("router_contract_safe_key", "safe-value")]


def test_main_app_setting_write_keeps_ctx_size_normalization(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "_resolve_ctx_size", lambda value: 2048)
    monkeypatch.setattr(
        main,
        "settings_set",
        lambda key, value: calls.append((key, value)),
    )
    client = TestClient(main.app)

    response = client.put("/settings/ctx_size", json={"value": "2048"})
    body = response.json()

    assert response.status_code == 200
    assert body == {"ok": True, "key": "ctx_size", "value": "2048"}
    assert calls == [("ctx_size", "2048")]
