from pathlib import Path

import main
from app.services import audio_runtime


SERVICE = Path("app/services/audio_runtime.py")
MAIN = Path("main.py")
AUDIO_ROUTER = Path("app/api/audio.py")


HELPERS = [
    "build_voice_status_payload",
    "build_asr_config_payload",
    "build_audio_runtime_debug_payload",
    "build_tts_status_payload",
    "normalize_audio_runtime_error",
    "classify_audio_runtime_degraded",
    "summarize_asr_runtime_state",
    "summarize_tts_runtime_state",
    "summarize_sbv2_runtime_state",
]


def _single_http_route(path: str, method: str):
    routes = [
        route
        for route in main.app.routes
        if getattr(route, "path", None) == path
        and method.upper() in getattr(route, "methods", set())
    ]
    assert len(routes) == 1, f"expected one {method} {path}, got {len(routes)}"
    return routes[0]


def _single_websocket_route(path: str):
    routes = [
        route
        for route in main.app.routes
        if getattr(route, "path", None) == path and not hasattr(route, "methods")
    ]
    assert len(routes) == 1, f"expected one websocket {path}, got {len(routes)}"
    return routes[0]


def test_audio_runtime_service_exposes_payload_helpers():
    for helper_name in HELPERS:
        assert hasattr(audio_runtime, helper_name), helper_name
        assert callable(getattr(audio_runtime, helper_name)), helper_name


def test_audio_runtime_service_remains_route_neutral_and_import_safe():
    text = SERVICE.read_text(encoding="utf-8")

    for forbidden in [
        "import main",
        "from main import",
        "APIRouter",
        "@router",
        "@app",
    ]:
        assert forbidden not in text

    top_level_imports = "\n".join(
        line for line in text.splitlines() if line.startswith(("import ", "from "))
    )
    for forbidden in [
        "import torch",
        "from torch",
        "import ctranslate2",
        "from ctranslate2",
        "import faster_whisper",
        "from faster_whisper",
        "style_bert_vits2_runtime",
        "StyleBertVITS2Runtime",
    ]:
        assert forbidden not in top_level_imports

    assert "detect_audio_runtime()" not in text


def test_audio_read_routes_move_to_audio_router_while_execution_stays_main():
    expected_audio_routes = [
        ("/voice/status", "GET", "voice_status_api"),
        ("/asr/config", "GET", "asr_config_api"),
        ("/audio/runtime/debug", "GET", "get_audio_runtime_debug_api"),
        ("/api/tts/style-bert-vits2/models", "GET", "api_style_bert_vits2_models"),
        ("/api/tts/style-bert-vits2/preview-normalization", "POST", "api_style_bert_vits2_preview_normalization"),
    ]
    for path, method, handler_name in expected_audio_routes:
        route = _single_http_route(path, method)
        assert route.endpoint.__module__ == "app.api.audio"
        assert route.endpoint.__name__ == handler_name

    expected_main_routes = [
        ("/voice/transcribe", "POST", "voice_transcribe_api"),
        ("/tts/synthesize", "POST", "tts_synthesize_api"),
        ("/tts/synthesize-batch", "POST", "tts_synthesize_batch_api"),
    ]
    for path, method, handler_name in expected_main_routes:
        route = _single_http_route(path, method)
        assert route.endpoint.__module__ == "main"
        assert route.endpoint.__name__ == handler_name

    route = _single_websocket_route("/echo/stream")
    assert route.endpoint.__module__ == "main"
    assert route.endpoint.__name__ == "echo_stream_ws"

    main_text = MAIN.read_text(encoding="utf-8")
    assert "audio_runtime_debug_provider" in main_text
    assert "voice_status_provider" in main_text
    assert '@router.get("/audio/runtime/debug")' in AUDIO_ROUTER.read_text(encoding="utf-8")


def test_response_shape_key_contract_for_extracted_helpers():
    voice_payload = audio_runtime.build_voice_status_payload(
        loaded=True,
        model="large-v3-turbo",
        device="cuda",
        compute_type="float16",
        last_cuda_error="",
        last_cuda_error_at="",
        lock_locked=False,
        candidates={"large-v3-turbo": []},
    )
    assert list(voice_payload.keys()) == [
        "loaded",
        "model",
        "device",
        "compute_type",
        "last_cuda_error",
        "last_cuda_error_at",
        "lock_locked",
        "candidates",
    ]

    asr_payload = audio_runtime.build_asr_config_payload(
        {
            "runtime": "runpod",
            "effective_engine": "faster_whisper",
            "effective_backend": "cuda",
            "asr_device": "cuda",
            "asr_compute_type": "float16",
        }
    )
    for key in [
        "runtime",
        "effective_engine",
        "effective_backend",
        "asr_device",
        "asr_compute_type",
    ]:
        assert key in asr_payload

    debug_payload = audio_runtime.build_audio_runtime_debug_payload(
        runtime_config={"runtime": "gpu", "tts_device": "cuda"},
        main_venv_cuda={"available": True},
        ctranslate2_cuda_available=True,
        sbv2_venv_cuda_probe={"available": True},
        asr_config={
            "asr_device": "cuda",
            "asr_compute_type": "float16",
            "effective_engine": "faster_whisper",
            "effective_backend": "cuda",
        },
        voice_status={
            "loaded": True,
            "last_cuda_error": "",
            "last_cuda_error_at": "",
            "lock_locked": False,
        },
        tts_status={
            "selected_device": "cuda",
            "requested_device": "auto",
            "effective_device": "cuda",
            "last_worker_error": {},
        },
    )
    assert list(debug_payload.keys()) == [
        "audio_runtime",
        "main_venv_cuda",
        "ctranslate2_cuda",
        "sbv2_venv_cuda_probe",
        "asr_selected",
        "tts_selected",
        "last_asr_cuda_error",
        "last_tts_worker_error",
        "audio_cuda_serialize_lock",
    ]
    assert debug_payload["asr_selected"] == {
        "device": "cuda",
        "compute_type": "float16",
        "effective_engine": "faster_whisper",
        "effective_backend": "cuda",
        "loaded": True,
    }
    assert debug_payload["tts_selected"] == {
        "device": "cuda",
        "requested_device": "auto",
        "effective_device": "cuda",
    }
