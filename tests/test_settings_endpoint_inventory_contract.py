from fastapi.testclient import TestClient

import main


def _routes_for(path: str, method: str) -> list:
    return [
        route
        for route in main.app.routes
        if getattr(route, "path", None) == path
        and method.upper() in getattr(route, "methods", set())
    ]


def _single_route(path: str, method: str):
    routes = _routes_for(path, method)
    assert len(routes) == 1
    return routes[0]


def _assert_representative_defaults_payload(body: dict) -> None:
    assert isinstance(body, dict)
    assert str(body["ctx_size"]).isdigit()
    assert body["search_enabled"] in {"true", "false"}
    assert body["streaming_enabled"] in {"true", "false"}
    assert body["feature_mode"] in {"model_orchestration", "ensemble"}


def test_main_app_core_settings_routes_are_owned_by_settings_router():
    expected = [
        ("/settings-defaults", "GET", "app.api.settings", "get_settings_defaults_api"),
        ("/settings", "GET", "app.api.settings", "get_settings_api"),
        ("/settings", "POST", "app.api.settings", "save_settings_api"),
        (
            "/settings/defaults",
            "GET",
            "app.api.settings",
            "get_settings_defaults_legacy_api",
        ),
        ("/settings/{key}", "GET", "app.api.settings", "get_setting_api"),
        ("/settings/{key}", "PUT", "app.api.settings", "set_setting_api"),
    ]

    for path, method, module_name, handler_name in expected:
        route = _single_route(path, method)
        assert route.endpoint.__module__ == module_name
        assert route.endpoint.__name__ == handler_name


def test_get_settings_defaults_alias_returns_representative_defaults():
    client = TestClient(main.app)

    response = client.get("/settings-defaults")
    body = response.json()

    assert response.status_code == 200
    _assert_representative_defaults_payload(body)


def test_get_settings_returns_representative_default_keys_without_fixing_full_body():
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


def test_get_setting_by_key_returns_safe_existing_key_without_db_write():
    client = TestClient(main.app)

    response = client.get("/settings/ctx_size")
    body = response.json()

    assert response.status_code == 200
    assert body["key"] == "ctx_size"
    assert str(body["value"]).isdigit()


def test_put_setting_route_is_owned_by_settings_router_without_executing_write():
    route = _single_route("/settings/{key}", "PUT")

    assert route.endpoint.__module__ == "app.api.settings"
    assert route.endpoint.__name__ == "set_setting_api"


def test_settings_defaults_literal_route_precedes_dynamic_key_route(monkeypatch):
    defaults_route = _single_route("/settings/defaults", "GET")
    settings_key_route = _single_route("/settings/{key}", "GET")

    assert main.app.routes.index(defaults_route) < main.app.routes.index(settings_key_route)

    monkeypatch.setattr(main, "settings_get", lambda key: f"shadowed:{key}")

    client = TestClient(main.app)
    response = client.get("/settings/defaults")
    body = response.json()

    assert response.status_code == 200
    _assert_representative_defaults_payload(body)
    assert body != {"key": "defaults", "value": "shadowed:defaults"}
    assert "key" not in body
    assert "value" not in body


def test_settings_defaults_literal_matches_alias_for_representative_keys():
    client = TestClient(main.app)

    legacy_response = client.get("/settings/defaults")
    alias_response = client.get("/settings-defaults")
    legacy_body = legacy_response.json()
    alias_body = alias_response.json()

    assert legacy_response.status_code == 200
    assert alias_response.status_code == 200
    for key in ("ctx_size", "search_enabled", "streaming_enabled", "feature_mode"):
        assert legacy_body[key] == alias_body[key]
