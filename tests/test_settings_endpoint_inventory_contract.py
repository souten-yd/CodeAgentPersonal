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


def test_main_app_settings_routes_are_still_owned_by_main_before_router_split():
    expected = [
        ("/settings", "GET", "get_settings_api"),
        ("/settings", "POST", "save_settings_api"),
        ("/settings/{key}", "GET", "get_setting_api"),
        ("/settings/{key}", "PUT", "set_setting_api"),
        ("/settings/defaults", "GET", "get_settings_defaults"),
    ]

    for path, method, handler_name in expected:
        route = _single_route(path, method)
        assert route.endpoint.__module__ == "main"
        assert route.endpoint.__name__ == handler_name


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


def test_put_setting_route_exists_but_contract_does_not_execute_write():
    route = _single_route("/settings/{key}", "PUT")

    assert route.endpoint.__module__ == "main"
    assert route.endpoint.__name__ == "set_setting_api"


def test_settings_defaults_currently_matches_dynamic_key_route_due_to_order(monkeypatch):
    settings_key_route = _single_route("/settings/{key}", "GET")
    defaults_route = _single_route("/settings/defaults", "GET")

    assert main.app.routes.index(settings_key_route) < main.app.routes.index(defaults_route)

    monkeypatch.setattr(main, "settings_get", lambda key: f"shadowed:{key}")

    client = TestClient(main.app)
    response = client.get("/settings/defaults")
    body = response.json()

    assert response.status_code == 200
    assert body == {"key": "defaults", "value": "shadowed:defaults"}
