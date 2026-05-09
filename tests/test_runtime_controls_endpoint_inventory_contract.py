from pathlib import Path

import main


INVENTORY_DOC = Path("docs/refactor_runtime_controls_api_inventory.md")


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


def test_runtime_controls_inventory_doc_exists_and_mentions_hotfix_diagnostics():
    text = INVENTORY_DOC.read_text(encoding="utf-8")

    required_paths = [
        "/llm/ctx",
        "/llm/props",
        "/search/status",
        "/streaming/status",
        "/audio/runtime/debug",
        "/runtime/cuda-debug",
        "/debug/model-startup",
        "/model/switch",
        "/model/auto-load",
        "/models/gguf/search",
        "/models/db/scan",
        "/models/db/benchmark/{mid}",
    ]
    for path in required_paths:
        assert path in text

    assert "PR4.39: Move read-only runtime status endpoints" in text
    assert "PR4.40: Move runtime diagnostics endpoints with provider fallback" in text
    assert "This PR does not move routes" in text


def test_read_only_runtime_candidates_still_belong_to_main_py():
    expected = [
        ("/llm/ctx", "GET", "get_ctx"),
        ("/llm/props", "GET", "llm_props"),
        ("/search/status", "GET", "search_status"),
        ("/streaming/status", "GET", "streaming_status"),
    ]

    for path, method, handler_name in expected:
        _assert_main_owner(path, method, handler_name)


def test_runtime_write_controls_still_belong_to_main_py_without_execution():
    expected = [
        ("/llm/ctx", "POST", "set_ctx"),
        ("/search/num", "POST", "search_set_num"),
        ("/search/enable", "POST", "search_enable"),
        ("/search/disable", "POST", "search_disable"),
        ("/streaming/enable", "POST", "streaming_enable"),
        ("/streaming/disable", "POST", "streaming_disable"),
        ("/model/switch", "POST", "model_switch"),
        ("/model/auto-load", "POST", "model_auto_load"),
    ]

    for path, method, handler_name in expected:
        _assert_main_owner(path, method, handler_name)


def test_hotfix_runtime_audio_cuda_diagnostics_still_belong_to_main_py():
    expected = [
        ("/runtime/cuda-debug", "GET", "runtime_cuda_debug"),
        ("/audio/runtime/debug", "GET", "audio_runtime_debug_api"),
        ("/debug/model-startup", "GET", "debug_model_startup"),
    ]

    for path, method, handler_name in expected:
        _assert_main_owner(path, method, handler_name)


def test_heavy_model_db_gguf_scan_and_benchmark_endpoints_remain_in_main_py():
    expected = [
        ("/models/hardware", "GET", "model_hardware_api"),
        ("/models/gguf/search", "GET", "search_gguf_models_api"),
        ("/models/gguf/download", "POST", "download_gguf_api"),
        ("/models/gguf/download/status", "GET", "gguf_download_status_api"),
        ("/models/db/scan", "POST", "scan_model_folder_api"),
        ("/models/db/scan/status", "GET", "model_scan_status_api"),
        ("/models/db/benchmark/{mid}", "POST", "benchmark_model_api"),
        ("/models/db/toggle/{mid}", "POST", "toggle_model_enabled"),
        ("/models/db/toggle_vlm/{mid}", "POST", "toggle_model_vlm_enabled"),
    ]

    for path, method, handler_name in expected:
        _assert_main_owner(path, method, handler_name)


def test_model_settings_router_endpoints_are_not_runtime_inventory_targets():
    moved_model_settings_routes = [
        ("/models/orchestration", "GET", "app.api.model_settings"),
        ("/models/roles", "GET", "app.api.model_settings"),
        ("/models/db", "GET", "app.api.model_settings"),
        ("/models/db/status", "GET", "app.api.model_settings"),
        ("/model/status", "GET", "app.api.model_settings"),
    ]

    for path, method, module_name in moved_model_settings_routes:
        route = _single_route(path, method)
        assert route.endpoint.__module__ == module_name

    text = INVENTORY_DOC.read_text(encoding="utf-8")
    assert "Already moved model-settings endpoints are out of scope" in text
