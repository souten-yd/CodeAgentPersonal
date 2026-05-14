from pathlib import Path
from types import SimpleNamespace

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
    "run_tts_synthesize_service_body",
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


class _DummyRuntime:
    def __init__(self):
        self.seen_req = None

    def synthesize(self, req):
        self.seen_req = dict(req)
        return b"RIFFdummy", "audio/wav"


class _DummyRegistry:
    def __init__(self):
        self.runtime = _DummyRuntime()

    def resolve_engine_key(self, raw_engine_key, requested_engine_key=None):
        assert raw_engine_key == "style_bert_vits2"
        assert requested_engine_key == "style_bert_vits2"
        return "style_bert_vits2"

    def get(self, raw_engine_key):
        assert raw_engine_key == "style_bert_vits2"
        return self.runtime


def test_tts_synthesize_service_body_uses_injected_dependencies_without_moving_route():
    debug_entries = []
    model_checks = []
    routed = []
    registry = _DummyRegistry()
    deps = audio_runtime.TtsSynthesizeServiceDependencies(
        engine_registry=registry,
        logger=SimpleNamespace(
            info=lambda *a, **k: None,
            warning=lambda *a, **k: None,
            error=lambda *a, **k: None,
        ),
        write_tts_debug_entry=lambda payload: debug_entries.append(dict(payload)),
        ensure_model_exists=lambda model, models_dir: model_checks.append((model, models_dir)),
        read_model_version=lambda _model_config_path: "2.0",
        apply_tts_language_routing=lambda req, model_version: routed.append((req, model_version))
        or "ja",
        style_bert_vits2_models_dir="/tmp/sbv2-models",
        request_id_factory=lambda: "req-fixed",
    )

    result = audio_runtime.run_tts_synthesize_service_body({"text": " hello "}, deps)

    assert result["audio_bytes"] == b"RIFFdummy"
    assert result["media_type"] == "audio/wav"
    assert result["request_id"] == "req-fixed"
    assert model_checks == [("koharune-ami", "/tmp/sbv2-models")]
    assert routed and routed[0][1] == "2.0"
    assert registry.runtime.seen_req["request_id"] == "req-fixed"
    assert registry.runtime.seen_req["engine"] == "style_bert_vits2"
    assert registry.runtime.seen_req["model"] == "koharune-ami"
    assert debug_entries[0]["stage"] == "route_enter"


def test_tts_synthesize_service_body_preserves_http_error_mapping():
    deps = audio_runtime.TtsSynthesizeServiceDependencies(
        engine_registry=_DummyRegistry(),
        logger=SimpleNamespace(
            info=lambda *a, **k: None,
            warning=lambda *a, **k: None,
            error=lambda *a, **k: None,
        ),
        write_tts_debug_entry=lambda _payload: None,
        ensure_model_exists=lambda _model, _models_dir: None,
        read_model_version=lambda _model_config_path: "2.0",
        apply_tts_language_routing=lambda _req, _model_version: "ja",
        style_bert_vits2_models_dir="/tmp/sbv2-models",
        request_id_factory=lambda: "req-fixed",
    )

    try:
        audio_runtime.run_tts_synthesize_service_body({"text": ""}, deps)
    except audio_runtime.AudioRuntimeHttpError as exc:
        assert exc.status_code == 400
        assert exc.detail == "text required"
    else:
        raise AssertionError("expected AudioRuntimeHttpError")


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
        "sbv2_runtime_policy",
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
