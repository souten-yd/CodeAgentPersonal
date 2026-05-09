from fastapi.testclient import TestClient

import main
from app.server import create_app


WRITE_PROVIDER_NAMES = [
    "search_enable_provider",
    "search_disable_provider",
    "search_num_provider",
    "streaming_enable_provider",
    "streaming_disable_provider",
    "runtime_llm_ctx_set_provider",
]


def test_create_app_lightweight_runtime_write_fallbacks_return_200_without_providers():
    app = create_app()
    client = TestClient(app)

    cases = [
        ("/search/enable", None, {"enabled": True}),
        ("/search/disable", None, {"enabled": False}),
        ("/search/num", {"num_results": 9}, {"num_results": 9}),
        ("/streaming/enable", None, {"enabled": True}),
        ("/streaming/disable", None, {"enabled": False}),
        ("/llm/ctx", {"n_ctx": 12288}, {"n_ctx": 12288}),
    ]

    for path, json_body, expected_body in cases:
        response = client.post(path, json=json_body) if json_body is not None else client.post(path)
        assert response.status_code == 200
        assert response.json() == expected_body

    for provider_name in WRITE_PROVIDER_NAMES:
        assert not hasattr(app.state, provider_name)


def test_create_app_write_fallbacks_do_not_touch_execution_or_heavy_runtime_providers():
    app = create_app()
    client = TestClient(app)

    forbidden_provider_names = [
        "runtime_llm_props_provider",
        "runtime_cuda_debug_provider",
        "audio_runtime_debug_provider",
        "model_startup_debug_provider",
        "model_manager_provider",
        "llm_http_provider",
        "searxng_process_provider",
        "asr_provider",
        "tts_provider",
        "filesystem_scan_provider",
        "job_execution_provider",
    ]

    def fail_if_touched(*args, **kwargs):
        raise AssertionError("fallback touched a forbidden runtime provider")

    for provider_name in forbidden_provider_names:
        setattr(app.state, provider_name, fail_if_touched)

    assert client.post("/search/enable").status_code == 200
    assert client.post("/search/disable").status_code == 200
    assert client.post("/search/num", json={"num_results": 3}).status_code == 200
    assert client.post("/streaming/enable").status_code == 200
    assert client.post("/streaming/disable").status_code == 200
    assert client.post("/llm/ctx", json={"n_ctx": 4096}).status_code == 200


def test_main_app_registers_lightweight_runtime_write_providers():
    for provider_name in WRITE_PROVIDER_NAMES:
        assert callable(getattr(main.app.state, provider_name))


def test_main_app_lightweight_runtime_write_response_shape_and_state(monkeypatch):
    monkeypatch.setattr(main, "_current_n_ctx", 8192)
    monkeypatch.setattr(main, "_search_enabled", False)
    monkeypatch.setattr(main, "_search_num_results", 5)
    monkeypatch.setattr(main, "_llm_streaming", False)

    client = TestClient(main.app)

    ctx_response = client.post("/llm/ctx", json={"n_ctx": 24576})
    search_num_response = client.post("/search/num", json={"num_results": 11})
    search_enable_response = client.post("/search/enable")
    search_disable_response = client.post("/search/disable")
    streaming_enable_response = client.post("/streaming/enable")
    streaming_disable_response = client.post("/streaming/disable")

    assert ctx_response.status_code == 200
    assert ctx_response.json() == {"n_ctx": 24576}
    assert main._current_n_ctx == 24576

    assert search_num_response.status_code == 200
    assert search_num_response.json() == {"num_results": 11}
    assert main._search_num_results == 11

    assert search_enable_response.status_code == 200
    assert search_enable_response.json() == {"enabled": True}

    assert search_disable_response.status_code == 200
    assert search_disable_response.json() == {"enabled": False}
    assert main._search_enabled is False

    assert streaming_enable_response.status_code == 200
    assert streaming_enable_response.json() == {"enabled": True}

    assert streaming_disable_response.status_code == 200
    assert streaming_disable_response.json() == {"enabled": False}
    assert main._llm_streaming is False


def test_main_app_lightweight_runtime_write_clamping_matches_existing_behavior(monkeypatch):
    monkeypatch.setattr(main, "_current_n_ctx", 8192)
    monkeypatch.setattr(main, "_search_num_results", 5)

    client = TestClient(main.app)

    assert client.post("/llm/ctx", json={"n_ctx": 1}).json() == {"n_ctx": 512}
    assert client.post("/search/num", json={"num_results": 999}).json() == {"num_results": 20}
