from pathlib import Path

from fastapi.testclient import TestClient

import main
from app.api import settings as settings_api
from app.server import create_app

MAIN_PY = Path("main.py")

SETTINGS_ROUTE_ORDER = [
    ("/settings-defaults", "GET"),
    ("/settings", "GET"),
    ("/settings", "POST"),
    ("/settings/defaults", "GET"),
    ("/settings/{key}", "GET"),
    ("/settings/{key}", "PUT"),
]

FORBIDDEN_MAIN_SETTINGS_DECORATORS = [
    '@app.get("/settings")',
    '@app.post("/settings")',
    '@app.get("/settings/defaults")',
    '@app.get("/settings/{key}")',
    '@app.put("/settings/{key}")',
    '@app.get("/settings-defaults")',
]


def _assert_representative_defaults_payload(body: dict) -> None:
    assert isinstance(body, dict)
    assert str(body["ctx_size"]).isdigit()
    assert body["search_enabled"] in {"true", "false"}
    assert body["streaming_enabled"] in {"true", "false"}
    assert body["feature_mode"] in {"model_orchestration", "ensemble"}


def _route_signature(route) -> tuple[str, str] | None:
    methods = getattr(route, "methods", set())
    for method in ("GET", "POST", "PUT"):
        if method in methods:
            return (route.path, method)
    return None


def _settings_route_order(app) -> list[tuple[str, str]]:
    wanted = set(SETTINGS_ROUTE_ORDER)
    return [
        signature
        for route in app.routes
        if (signature := _route_signature(route)) in wanted
    ]


def _single_route(app, path: str, method: str):
    routes = [
        route
        for route in app.routes
        if getattr(route, "path", None) == path
        and method.upper() in getattr(route, "methods", set())
    ]
    assert len(routes) == 1
    return routes[0]


def test_settings_router_declares_static_defaults_routes_before_key_route():
    assert _settings_route_order(create_app()) == SETTINGS_ROUTE_ORDER

    legacy_defaults_index = SETTINGS_ROUTE_ORDER.index(("/settings/defaults", "GET"))
    key_route_index = SETTINGS_ROUTE_ORDER.index(("/settings/{key}", "GET"))
    assert legacy_defaults_index < key_route_index


def test_create_app_registers_settings_router_once_with_settings_owner():
    app = create_app()

    for path, method in SETTINGS_ROUTE_ORDER:
        route = _single_route(app, path, method)
        assert route.endpoint.__module__ == "app.api.settings"


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


def test_create_app_setting_by_key_returns_single_key_fallback_payload():
    client = TestClient(create_app())

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
    assert body.get("key") != "defaults"
    assert "value" not in body


def test_create_app_settings_defaults_legacy_route_returns_defaults_map_not_key_shadow():
    client = TestClient(create_app())

    response = client.get("/settings/defaults")
    body = response.json()

    assert response.status_code == 200
    _assert_representative_defaults_payload(body)
    assert body.get("key") != "defaults"
    assert "value" not in body


def test_create_app_setting_write_returns_conservative_echo_without_db_write(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "settings_set", lambda key, value: calls.append((key, value)))
    client = TestClient(create_app())

    response = client.put("/settings/test_key", json={"value": "factory-value"})
    body = response.json()

    assert response.status_code == 200
    assert body == {"ok": True, "key": "test_key", "value": "factory-value"}
    assert calls == []


def test_create_app_bulk_settings_write_returns_conservative_echo_without_db_or_runtime_side_effects(
    monkeypatch,
):
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


def test_main_app_settings_providers_are_registered_and_callable():
    for provider_name in (
        "settings_get_all_provider",
        "settings_get_provider",
        "settings_defaults_provider",
        "settings_set_provider",
        "settings_bulk_save_provider",
    ):
        assert callable(getattr(main.app.state, provider_name, None))


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


def test_main_app_setting_by_key_uses_existing_key_value_provider():
    client = TestClient(main.app)

    response = client.get("/settings/ctx_size")
    body = response.json()

    assert response.status_code == 200
    assert body["key"] == "ctx_size"
    assert str(body["value"]).isdigit()


def test_main_app_settings_defaults_alias_matches_settings_defaults_constant():
    client = TestClient(main.app)

    response = client.get("/settings-defaults")
    body = response.json()

    assert response.status_code == 200
    assert body == dict(main.SETTINGS_DEFAULTS)


def test_main_app_settings_defaults_legacy_route_uses_defaults_provider_not_key_shadow():
    client = TestClient(main.app)

    response = client.get("/settings/defaults")
    body = response.json()

    assert response.status_code == 200
    assert body == dict(main.SETTINGS_DEFAULTS)
    assert body.get("key") != "defaults"
    assert "value" not in body


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


def test_settings_routes_are_owned_by_settings_module_on_production_app():
    for path, method in SETTINGS_ROUTE_ORDER:
        route = _single_route(main.app, path, method)
        assert route.endpoint.__module__ == "app.api.settings"


def test_main_py_does_not_reintroduce_settings_route_decorators():
    source = MAIN_PY.read_text(encoding="utf-8")

    for decorator in FORBIDDEN_MAIN_SETTINGS_DECORATORS:
        assert decorator not in source


def test_settings_router_exposes_declared_provider_helpers():
    for helper_name in (
        "get_settings_get_all_provider",
        "get_settings_get_provider",
        "get_settings_defaults_provider",
        "get_settings_set_provider",
        "get_settings_bulk_save_provider",
    ):
        assert callable(getattr(settings_api, helper_name))
