from pathlib import Path

import main


INVENTORY_DOC = Path("docs/refactor_remaining_main_routes_inventory.md")


def _routes_for(path: str, method: str) -> list:
    return [
        route
        for route in main.app.routes
        if getattr(route, "path", None) == path
        and method.upper() in getattr(route, "methods", set())
    ]


def _websocket_routes_for(path: str) -> list:
    return [
        route
        for route in main.app.routes
        if getattr(route, "path", None) == path
        and not hasattr(route, "methods")
    ]


def _single_route(path: str, method: str):
    routes = _routes_for(path, method)
    assert len(routes) == 1
    return routes[0]


def _single_websocket_route(path: str):
    routes = _websocket_routes_for(path)
    assert len(routes) == 1
    return routes[0]


def _assert_route_owner(path: str, method: str, module_name: str, handler_name: str):
    route = _single_route(path, method)
    assert route.endpoint.__module__ == module_name
    assert route.endpoint.__name__ == handler_name
    return route


def _assert_main_owner(path: str, method: str, handler_name: str):
    return _assert_route_owner(path, method, "main", handler_name)


def test_remaining_main_routes_inventory_doc_exists_and_names_next_pr_sequence():
    text = INVENTORY_DOC.read_text(encoding="utf-8")

    required_sections = [
        "A. Already moved / out of scope",
        "B. System read-only status after PR4.42",
        "C. Settings candidates",
        "D. Project / file / job candidates",
        "E. Nexus candidates",
        "F. Echo / audio candidates",
        "G. Model write/heavy candidates",
        "H. UI/static candidates",
        "PR4.42: Move low-risk system read-only endpoints into `app/api/system_status.py`",
        "PR4.43: Move project read-only endpoints into `app/api/projects.py`",
        "PR4.44: Move project/job read-only status endpoints into `app/api/jobs.py`",
        "PR4.45以降",
    ]
    for section in required_sections:
        assert section in text

    required_paths = [
        "/health",
        "/system/summary",
        "/system/usage",
        "/system/usage/debug",
        "/settings",
        "/settings-defaults",
        "/settings/{key}",
        "/projects",
        "/projects/{project}/history",
        "/projects/{project}/files",
        "/projects/{project}/jobs",
        "/jobs/submit",
        "/jobs/{job_id}/poll",
        "/nexus/*",
        "/echo/stream",
        "/voice/transcribe",
        "/tts/synthesize",
        "/model/switch",
        "/model/auto-load",
        "/models/gguf/search",
        "/models/db/scan",
        "/models/db/benchmark/{mid}",
        "/debug/llama",
        "/static/*",
        "/favicon",
    ]
    for path in required_paths:
        assert path in text


def test_already_moved_read_only_model_settings_and_runtime_routes_do_not_return_to_main_py():
    moved_routes = [
        ("/models/orchestration", "GET", "app.api.model_settings", "get_model_orchestration_api"),
        ("/models/roles", "GET", "app.api.model_settings", "get_model_role_assignments_api"),
        ("/models/db", "GET", "app.api.model_settings", "list_models_db_api"),
        ("/models/db/status", "GET", "app.api.model_settings", "get_model_db_status_api"),
        ("/model/status", "GET", "app.api.model_settings", "get_model_manager_status_api"),
        ("/llm/ctx", "GET", "app.api.runtime_controls", "get_runtime_llm_ctx_api"),
        ("/llm/props", "GET", "app.api.runtime_controls", "get_runtime_llm_props_api"),
        ("/search/status", "GET", "app.api.runtime_controls", "get_search_status_api"),
        ("/streaming/status", "GET", "app.api.runtime_controls", "get_streaming_status_api"),
        ("/runtime/cuda-debug", "GET", "app.api.runtime_controls", "get_runtime_cuda_debug_api"),
        ("/audio/runtime/debug", "GET", "app.api.runtime_controls", "get_audio_runtime_debug_api"),
        ("/debug/model-startup", "GET", "app.api.runtime_controls", "get_model_startup_debug_api"),
    ]

    for path, method, module_name, handler_name in moved_routes:
        _assert_route_owner(path, method, module_name, handler_name)


def test_system_status_and_settings_router_routes_are_out_of_scope_for_this_pr():
    expected = [
        ("/health", "GET", "app.api.system_status", "health"),
        ("/system/summary", "GET", "app.api.system_status", "system_summary"),
        ("/system/usage", "GET", "app.api.system_status", "system_usage"),
        ("/system/usage/debug", "GET", "main", "system_usage_debug_payload"),
        ("/settings-defaults", "GET", "app.api.settings", "get_settings_defaults_api"),
        ("/settings", "GET", "app.api.settings", "get_settings_api"),
        ("/settings", "POST", "app.api.settings", "save_settings_api"),
        ("/settings/{key}", "GET", "app.api.settings", "get_setting_api"),
        ("/settings/{key}", "PUT", "app.api.settings", "set_setting_api"),
    ]

    for path, method, module_name, handler_name in expected:
        _assert_route_owner(path, method, module_name, handler_name)


def test_model_write_and_heavy_diagnostic_routes_remain_in_main_py():
    expected = [
        ("/debug/llama", "GET", "debug_llama"),
        ("/model/switch", "POST", "model_switch"),
        ("/model/auto-load", "POST", "model_auto_load"),
        ("/models/gguf/search", "GET", "search_gguf_models_api"),
        ("/models/db/scan", "POST", "scan_model_folder_api"),
        ("/models/db/benchmark/{mid}", "POST", "benchmark_model_api"),
    ]

    for path, method, handler_name in expected:
        _assert_main_owner(path, method, handler_name)


def test_echo_stream_websocket_remains_in_main_py():
    route = _single_websocket_route("/echo/stream")
    assert route.endpoint.__module__ == "main"
    assert route.endpoint.__name__ == "echo_stream_ws"


def test_write_and_heavy_job_routes_remain_in_main_py():
    expected = [
        ("/jobs/submit", "POST", "submit_job"),
        ("/jobs/{job_id}", "GET", "get_job"),
        ("/jobs/{job_id}/stream", "GET", "stream_job"),
        ("/jobs/{job_id}/respond", "POST", "respond_to_job"),
        ("/jobs/{job_id}/logs", "GET", "get_job_logs_api"),
        ("/jobs/{job_id}/analyze_skills", "POST", "analyze_job_for_skills"),
    ]

    for path, method, handler_name in expected:
        _assert_main_owner(path, method, handler_name)


def test_project_read_only_routes_moved_to_projects_router_while_writes_stay_main_owned():
    moved_routes = [
        ("/projects", "GET", "app.api.projects", "get_projects_api"),
        ("/projects/{project}/files", "GET", "app.api.projects", "get_project_files_api"),
        ("/projects/{project}/history", "GET", "app.api.projects", "get_project_history_api"),
    ]
    for path, method, module_name, handler_name in moved_routes:
        _assert_route_owner(path, method, module_name, handler_name)

    _assert_main_owner("/projects", "POST", "create_project")


def test_job_read_only_status_routes_moved_to_jobs_router_while_submit_stays_main_owned():
    moved_routes = [
        ("/projects/{project}/jobs", "GET", "app.api.jobs", "get_project_jobs_api"),
        ("/jobs/{job_id}/poll", "GET", "app.api.jobs", "get_job_poll_api"),
    ]
    for path, method, module_name, handler_name in moved_routes:
        _assert_route_owner(path, method, module_name, handler_name)

    _assert_main_owner("/jobs/submit", "POST", "submit_job")
