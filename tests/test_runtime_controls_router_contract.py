from types import SimpleNamespace

from fastapi.testclient import TestClient

import main
from app.api.audio import default_audio_runtime_debug_payload
from app.api.runtime_controls import default_runtime_cuda_debug_payload
from app.server import create_app


def test_create_app_runtime_controls_fallbacks_return_safe_payloads():
    client = TestClient(create_app())

    ctx_response = client.get("/llm/ctx")
    props_response = client.get("/llm/props")
    search_response = client.get("/search/status")
    streaming_response = client.get("/streaming/status")
    cuda_response = client.get("/runtime/cuda-debug")
    audio_response = client.get("/audio/runtime/debug")
    model_startup_response = client.get("/debug/model-startup")

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

    assert cuda_response.status_code == 200
    assert cuda_response.json() == default_runtime_cuda_debug_payload()

    assert audio_response.status_code == 200
    assert audio_response.json() == default_audio_runtime_debug_payload()

    assert model_startup_response.status_code == 200
    assert model_startup_response.json() == {
        "status": "unavailable",
        "hints": [],
        "log_tail": "",
        "note": "model startup provider unavailable",
    }


def test_main_app_runtime_controls_use_provider_backed_existing_payloads(monkeypatch):
    monkeypatch.setattr(main, "_current_n_ctx", 24576)
    monkeypatch.setattr(main, "_search_enabled", True)
    monkeypatch.setattr(main, "_search_num_results", 7)
    monkeypatch.setattr(main, "_llm_streaming", True)

    cuda_debug_payload = {
        "intended_backend": "cuda",
        "runpod_detected": True,
        "gpu_validation_status": "ok",
    }
    monkeypatch.setattr(main._model_manager, "cuda_debug_dict", lambda: cuda_debug_payload)
    monkeypatch.setattr(main._model_manager, "_last_startup_hints", ["hint from manager"])
    monkeypatch.setattr(main._model_manager, "llama_path", "/tmp/llama-server")
    monkeypatch.setattr(main._model_manager, "_last_start_cmd", ["llama-server", "--ngl", "99"])
    monkeypatch.setattr(main, "LLAMA_STARTUP_LOG_PATH", "/tmp/nonexistent-codeagent-test.log")

    runtime_cfg = SimpleNamespace(
        ctranslate2_cuda_available=True,
        tts_device="cuda",
        to_dict=lambda: {"runtime": "gpu", "tts_device": "cuda"},
    )
    monkeypatch.setattr(main, "detect_audio_runtime", lambda: runtime_cfg)
    monkeypatch.setattr(
        main,
        "_resolve_asr_runtime_config",
        lambda: {
            "asr_device": "cuda",
            "asr_compute_type": "float16",
            "effective_engine": "whisper_cpp",
            "effective_backend": "ctranslate2",
        },
    )
    monkeypatch.setattr(
        main,
        "voice_status",
        lambda: {
            "loaded": True,
            "last_cuda_error": "",
            "last_cuda_error_at": "",
            "lock_locked": False,
        },
    )
    monkeypatch.setattr(main, "_probe_main_torch_cuda", lambda: {"available": True})
    monkeypatch.setattr(main, "_probe_sbv2_venv_cuda", lambda: {"available": True})

    class _FakeTtsEngine:
        def status(self):
            return {
                "selected_device": "cuda",
                "requested_device": "auto",
                "effective_device": "cuda",
                "last_worker_error": {},
            }

    monkeypatch.setattr(main._tts_engine_registry, "get", lambda raw_engine_key: _FakeTtsEngine())

    def raise_if_called(*args, **kwargs):
        raise RuntimeError("live llama-server unavailable in test")

    monkeypatch.setattr(main.requests, "get", raise_if_called)

    client = TestClient(main.app)

    ctx_response = client.get("/llm/ctx")
    props_response = client.get("/llm/props")
    search_response = client.get("/search/status")
    streaming_response = client.get("/streaming/status")
    cuda_response = client.get("/runtime/cuda-debug")
    audio_response = client.get("/audio/runtime/debug")
    model_startup_response = client.get("/debug/model-startup")

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

    assert cuda_response.status_code == 200
    assert cuda_response.json() == cuda_debug_payload

    assert audio_response.status_code == 200
    audio_body = audio_response.json()
    assert audio_body["audio_runtime"] == {"runtime": "gpu", "tts_device": "cuda"}
    assert audio_body["main_venv_cuda"] == {"available": True}
    assert audio_body["ctranslate2_cuda"] == {"available": True}
    assert audio_body["sbv2_venv_cuda_probe"] == {"available": True}
    assert audio_body["asr_selected"] == {
        "device": "cuda",
        "compute_type": "float16",
        "effective_engine": "whisper_cpp",
        "effective_backend": "ctranslate2",
        "loaded": True,
    }
    assert audio_body["tts_selected"] == {
        "device": "cuda",
        "requested_device": "auto",
        "effective_device": "cuda",
    }

    assert model_startup_response.status_code == 200
    model_startup_body = model_startup_response.json()
    assert model_startup_body["llama_path"] == "/tmp/llama-server"
    assert model_startup_body["last_start_cmd"] == ["llama-server", "--ngl", "99"]
    assert model_startup_body["hints"] == ["hint from manager"]
    assert model_startup_body["log_path"] == "/tmp/nonexistent-codeagent-test.log"
    assert model_startup_body["log_tail"] == ""
    assert model_startup_body["runtime_cuda_debug"] == cuda_debug_payload
