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


def _assert_main_owner(path: str, method: str, handler_name: str):
    route = _single_route(path, method)
    assert route.endpoint.__module__ == "main"
    assert route.endpoint.__name__ == handler_name
    return route


def test_model_settings_inventory_current_route_owners_are_still_main_py():
    expected = [
        ("/models/orchestration", "GET", "get_model_orchestration_api"),
        ("/models/orchestration", "POST", "save_model_orchestration_api"),
        ("/models/roles", "GET", "get_model_role_assignments_api"),
        ("/models/roles", "POST", "save_model_role_assignments_api"),
        ("/ensemble/settings", "GET", "get_ensemble_settings_api"),
        ("/ensemble/settings", "POST", "save_ensemble_settings_api"),
        ("/ensemble/vram", "GET", "get_ensemble_vram_api"),
        ("/models/db", "GET", "list_models_db_api"),
        ("/models/db", "POST", "add_model_db_api"),
        ("/models/db/{mid}", "PUT", "update_model_db_api"),
        ("/models/db/{mid}", "DELETE", "delete_model_db_api"),
        ("/models/db/status", "GET", "model_db_status_api"),
        ("/models/hardware", "GET", "model_hardware_api"),
        ("/models/gguf/search", "GET", "search_gguf_models_api"),
        ("/models/gguf/download", "POST", "download_gguf_api"),
        ("/models/gguf/download/status", "GET", "gguf_download_status_api"),
        ("/models/db/scan", "POST", "scan_model_folder_api"),
        ("/models/db/scan/status", "GET", "model_scan_status_api"),
        ("/models/db/benchmark/{mid}", "POST", "benchmark_model_api"),
        ("/models/db/toggle/{mid}", "POST", "toggle_model_enabled"),
        ("/models/db/toggle_vlm/{mid}", "POST", "toggle_model_vlm_enabled"),
        ("/model/status", "GET", "model_status"),
        ("/model/switch", "POST", "model_switch"),
        ("/model/auto-load", "POST", "model_auto_load"),
        ("/llm/props", "GET", "llm_props"),
        ("/llm/ctx", "GET", "get_ctx"),
        ("/llm/ctx", "POST", "set_ctx"),
        ("/search/status", "GET", "search_status"),
        ("/search/num", "POST", "search_set_num"),
        ("/search/enable", "POST", "search_enable"),
        ("/search/disable", "POST", "search_disable"),
        ("/streaming/status", "GET", "streaming_status"),
        ("/streaming/enable", "POST", "streaming_enable"),
        ("/streaming/disable", "POST", "streaming_disable"),
    ]

    for path, method, handler_name in expected:
        _assert_main_owner(path, method, handler_name)


def test_read_only_orchestration_endpoint_contract_without_db_writes(monkeypatch):
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
    assert body["feature_mode"] == "model_orchestration"
    assert body["policy"] == "ladder_fail_and_quality"
    assert body["quality_check_enabled"] is True
    assert body["resolved_ladder"] == ["coder-a", "coder-b"]
    assert isinstance(body["models"], list)
    assert body["models"][0]["model_key"] == "coder-a"
    assert isinstance(body["models"][0]["tok_per_sec"], float)


def test_read_only_model_roles_endpoint_contract_without_db_writes(monkeypatch):
    monkeypatch.setattr(main, "MODEL_ROLE_OPTIONS", ("plan", "code", "chat"))
    monkeypatch.setattr(main, "settings_get", lambda key: "coder-a" if key == "role_model_plan" else "")
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
    monkeypatch.setattr(main, "_get_auto_role_model_map", lambda catalog: {"code": "coder-b"})
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
    assert body["roles"] == ["plan", "code", "chat"]
    assert body["planner_key"] == "coder-a"
    assert body["assignments"]["plan"] == {"model_key": "coder-a", "source": "explicit"}
    assert body["assignments"]["code"] == {"model_key": "coder-b", "source": "auto"}
    assert isinstance(body["models"], list)
    assert body["models"][0]["ctx_size"] == 4096
    assert body["models"][0]["auto_roles"] == ["plan", "chat"]


def test_read_only_ensemble_settings_and_vram_contract(monkeypatch):
    status_payload = {
        "configured_mode": "parallel",
        "recommended_mode": "serial",
        "auto_switch_on_low_vram": True,
        "warning": True,
        "free_vram_mb": 1024,
        "required_vram_parallel_mb": 4096,
        "required_vram_serial_mb": 2048,
        "models": [],
        "hardware": {"gpu_backend": "test"},
    }
    monkeypatch.setattr(main, "get_ensemble_resource_status", lambda: dict(status_payload))

    client = TestClient(main.app)
    settings_response = client.get("/ensemble/settings")
    settings_body = settings_response.json()
    vram_response = client.get("/ensemble/vram")
    vram_body = vram_response.json()

    assert settings_response.status_code == 200
    assert settings_body["execution_mode"] == "parallel"
    assert settings_body["auto_switch_on_low_vram"] is True
    assert settings_body["status"]["recommended_mode"] == "serial"
    assert vram_response.status_code == 200
    assert vram_body["configured_mode"] == "parallel"
    assert isinstance(vram_body["models"], list)
    assert isinstance(vram_body["hardware"], dict)


def test_read_only_model_db_and_runtime_status_contract(monkeypatch):
    monkeypatch.setattr(main, "model_db_exists", lambda: True)
    monkeypatch.setattr(
        main,
        "model_db_list",
        lambda: [
            {"id": "m1", "tok_per_sec": 1.0, "is_vlm": 0, "ctx_size": "4096"},
            {"id": "m2", "tok_per_sec": -1, "is_vlm": 1, "ctx_size": "8192"},
        ],
    )
    monkeypatch.setattr(main, "MODEL_DB_PATH", "/tmp/test-models.db")

    class FakeModelManager:
        def status_dict(self):
            return {"status": "ready", "current_key": "coder-a", "catalog": {}}

    monkeypatch.setattr(main, "_model_manager", FakeModelManager())

    client = TestClient(main.app)
    db_status_response = client.get("/models/db/status")
    db_status_body = db_status_response.json()
    model_status_response = client.get("/model/status")
    model_status_body = model_status_response.json()
    ctx_response = client.get("/llm/ctx")
    search_response = client.get("/search/status")
    streaming_response = client.get("/streaming/status")

    assert db_status_response.status_code == 200
    assert db_status_body["db_exists"] is True
    assert db_status_body["has_models"] is True
    assert db_status_body["total"] == 2
    assert db_status_body["benchmarked"] == 1
    assert db_status_body["has_vlm"] is True
    assert isinstance(db_status_body["db_path"], str)
    assert model_status_response.status_code == 200
    assert model_status_body["status"] == "ready"
    assert model_status_body["current_key"] == "coder-a"
    assert ctx_response.status_code == 200
    assert isinstance(ctx_response.json()["n_ctx"], int)
    assert search_response.status_code == 200
    assert isinstance(search_response.json()["enabled"], bool)
    assert isinstance(search_response.json()["num_results"], int)
    assert streaming_response.status_code == 200
    assert isinstance(streaming_response.json()["enabled"], bool)


def test_write_and_heavy_probe_routes_exist_without_executing_side_effects():
    write_or_heavy_routes = [
        ("/models/orchestration", "POST"),
        ("/models/roles", "POST"),
        ("/ensemble/settings", "POST"),
        ("/models/db", "POST"),
        ("/models/db/{mid}", "PUT"),
        ("/models/db/{mid}", "DELETE"),
        ("/models/gguf/search", "GET"),
        ("/models/gguf/download", "POST"),
        ("/models/db/scan", "POST"),
        ("/models/db/benchmark/{mid}", "POST"),
        ("/models/db/toggle/{mid}", "POST"),
        ("/models/db/toggle_vlm/{mid}", "POST"),
        ("/model/switch", "POST"),
        ("/model/auto-load", "POST"),
        ("/llm/props", "GET"),
        ("/llm/ctx", "POST"),
        ("/search/num", "POST"),
        ("/search/enable", "POST"),
        ("/search/disable", "POST"),
        ("/streaming/enable", "POST"),
        ("/streaming/disable", "POST"),
    ]

    for path, method in write_or_heavy_routes:
        assert _routes_for(path, method), f"missing {method} {path}"
