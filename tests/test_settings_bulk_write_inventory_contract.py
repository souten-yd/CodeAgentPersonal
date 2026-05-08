from fastapi.testclient import TestClient

import main


def _single_route(path: str, method: str):
    routes = [
        route
        for route in main.app.routes
        if getattr(route, "path", None) == path
        and method.upper() in getattr(route, "methods", set())
    ]
    assert len(routes) == 1
    return routes[0]


def test_post_settings_route_owner_stays_in_main_before_provider_split():
    route = _single_route("/settings", "POST")

    assert route.endpoint.__module__ == "main"
    assert route.endpoint.__name__ == "save_settings_api"


def test_post_settings_response_shape_and_side_effect_paths_without_db_write(monkeypatch):
    bulk_writes = []
    asr_applies = []
    ensemble_syncs = []
    ensemble_guards = []

    monkeypatch.setattr(main, "_resolve_ctx_size", lambda value: 4096)
    monkeypatch.setattr(main, "_get_summary_token_limit", lambda: 400)
    monkeypatch.setattr(
        main,
        "settings_set_bulk",
        lambda req: bulk_writes.append(dict(req)),
    )
    monkeypatch.setattr(
        main,
        "_apply_asr_runtime_settings",
        lambda req: asr_applies.append(dict(req)),
    )
    monkeypatch.setattr(
        main,
        "_sync_ensemble_settings_to_opencode_json",
        lambda: ensemble_syncs.append("sync"),
    )
    monkeypatch.setattr(
        main,
        "_apply_ensemble_execution_mode_guard",
        lambda: ensemble_guards.append("guard"),
    )
    monkeypatch.setattr(main, "_search_enabled", False)
    monkeypatch.setattr(main, "_llm_streaming", True)
    monkeypatch.setattr(main, "_current_n_ctx", 1024)

    client = TestClient(main.app)
    response = client.post(
        "/settings",
        json={
            "max_output_tokens": "999",
            "llm_port": "1234",
            "ctx_size": "not-directly-used",
            "summary_max_tokens": "999",
            "read_file_inject_max_chars": "2000",
            "ensemble_execution_mode": "SERIAL",
            "ensemble_auto_switch_on_low_vram": "off",
            "asr_engine": "whisper_cpp",
            "search_enabled": "yes",
            "streaming_enabled": "false",
        },
    )
    body = response.json()

    expected_saved = [
        "ctx_size",
        "summary_max_tokens",
        "read_file_inject_max_chars",
        "ensemble_execution_mode",
        "ensemble_auto_switch_on_low_vram",
        "asr_engine",
        "search_enabled",
        "streaming_enabled",
    ]
    expected_write = {
        "ctx_size": "4096",
        "summary_max_tokens": "400",
        "read_file_inject_max_chars": "4000",
        "ensemble_execution_mode": "serial",
        "ensemble_auto_switch_on_low_vram": "false",
        "asr_engine": "whisper_cpp",
        "search_enabled": "yes",
        "streaming_enabled": "false",
    }

    assert response.status_code == 200
    assert body == {"ok": True, "saved": expected_saved}
    assert bulk_writes == [expected_write]
    assert asr_applies == [expected_write]
    assert ensemble_syncs == ["sync"]
    assert ensemble_guards == ["guard"]
    assert main._search_enabled is True
    assert main._llm_streaming is False
    assert main._current_n_ctx == 4096
