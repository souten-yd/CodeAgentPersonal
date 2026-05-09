from fastapi.testclient import TestClient

import main
from app.server import create_app


def test_create_app_runtime_controls_fallbacks_return_safe_payloads():
    client = TestClient(create_app())

    ctx_response = client.get("/llm/ctx")
    props_response = client.get("/llm/props")
    search_response = client.get("/search/status")
    streaming_response = client.get("/streaming/status")

    assert ctx_response.status_code == 200
    assert ctx_response.json() == {"n_ctx": 0, "ctx_size": 0}

    assert props_response.status_code == 200
    assert props_response.json() == {
        "n_ctx": 0,
        "n_ctx_runtime": 0,
        "n_ctx_train": 0,
        "raw": {},
        "note": "runtime provider unavailable",
    }

    assert search_response.status_code == 200
    assert search_response.json() == {"enabled": False, "num_results": 5}

    assert streaming_response.status_code == 200
    assert streaming_response.json() == {"enabled": False}


def test_main_app_runtime_controls_use_provider_backed_existing_payloads(monkeypatch):
    monkeypatch.setattr(main, "_current_n_ctx", 24576)
    monkeypatch.setattr(main, "_search_enabled", True)
    monkeypatch.setattr(main, "_search_num_results", 7)
    monkeypatch.setattr(main, "_llm_streaming", True)

    def raise_if_called(*args, **kwargs):
        raise RuntimeError("live llama-server unavailable in test")

    monkeypatch.setattr(main.requests, "get", raise_if_called)

    client = TestClient(main.app)

    ctx_response = client.get("/llm/ctx")
    props_response = client.get("/llm/props")
    search_response = client.get("/search/status")
    streaming_response = client.get("/streaming/status")

    assert ctx_response.status_code == 200
    assert ctx_response.json() == {"n_ctx": 24576}

    assert props_response.status_code == 200
    props_body = props_response.json()
    assert props_body["n_ctx"] == 65535
    assert props_body["n_ctx_runtime"] == 24576
    assert props_body["note"] == "using server default"

    assert search_response.status_code == 200
    assert search_response.json() == {"enabled": True, "num_results": 7}

    assert streaming_response.status_code == 200
    assert streaming_response.json() == {"enabled": True}
