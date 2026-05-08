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


def test_create_app_settings_defaults_legacy_route_returns_conservative_fallback_payload():
    client = TestClient(create_app())

    response = client.get("/settings/defaults")
    body = response.json()

    assert response.status_code == 200
    _assert_representative_defaults_payload(body)
    assert body.get("key") != "defaults"
    assert "value" not in body


def test_main_app_settings_defaults_legacy_route_uses_existing_defaults_provider():
    client = TestClient(main.app)

    response = client.get("/settings/defaults")
    body = response.json()

    assert response.status_code == 200
    _assert_representative_defaults_payload(body)
    assert body.get("key") != "defaults"
    assert "value" not in body


def test_create_app_setting_write_returns_conservative_fallback_without_db_write():
    client = TestClient(create_app())

    response = client.put("/settings/test_key", json={"value": "factory-value"})
    body = response.json()

    assert response.status_code == 200
    assert body == {"ok": True, "key": "test_key", "value": "factory-value"}


def test_create_app_bulk_settings_write_returns_conservative_fallback_without_db_write(monkeypatch):
    unexpected_calls = []
    monkeypatch.setattr(
        main,
        "settings_set_bulk",
        lambda req: unexpected_calls.append(("settings_set_bulk", dict(req))),
    )
    monkeypatch.setattr(
        main,
        "_apply_asr_runtime_settings",
        lambda req: unexpected_calls.append(("asr", dict(req))),
    )
    monkeypatch.setattr(
        main,
        "_sync_ensemble_settings_to_opencode_json",
        lambda: unexpected_calls.append(("ensemble_sync", None)),
    )
    monkeypatch.setattr(
        main,
        "_apply_ensemble_execution_mode_guard",
        lambda: unexpected_calls.append(("ensemble_guard", None)),
    )
    app = create_app()
    assert not hasattr(app.state, "settings_bulk_save_provider")
    client = TestClient(app)

    response = client.post(
        "/settings",
        json={
            "ctx_size": "not-normalized-in-fallback",
            "asr_engine": "whisper_cpp",
            "ensemble_execution_mode": "serial",
        },
    )
    body = response.json()

    assert response.status_code == 200
    assert body == {
        "ok": True,
        "saved": ["ctx_size", "asr_engine", "ensemble_execution_mode"],
    }
    assert unexpected_calls == []


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
