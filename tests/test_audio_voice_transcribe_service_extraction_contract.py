import base64
import importlib
from pathlib import Path
from types import SimpleNamespace

import main
from app.services import audio_runtime


SERVICE = Path("app/services/audio_runtime.py")
MAIN = Path("main.py")


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


def test_transcribe_service_symbols_exist_and_audio_runtime_stays_route_neutral():
    assert hasattr(audio_runtime, "VoiceTranscribeServiceDependencies")
    assert hasattr(audio_runtime, "VoiceTranscribeServiceResponse")
    assert hasattr(audio_runtime, "run_voice_transcribe_service_body")
    assert callable(audio_runtime.run_voice_transcribe_service_body)

    text = SERVICE.read_text(encoding="utf-8")
    for forbidden in ["import main", "from main import", "APIRouter", "@router", "@app"]:
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
    ]:
        assert forbidden not in top_level_imports


def test_voice_transcribe_load_and_echo_stream_route_owners_remain_main_py():
    expected_main_routes = [
        ("/voice/transcribe", "POST", "voice_transcribe_api"),
        ("/voice/load", "POST", "voice_load_api"),
    ]
    for path, method, handler_name in expected_main_routes:
        route = _single_http_route(path, method)
        assert route.endpoint.__module__ == "main"
        assert route.endpoint.__name__ == handler_name

    echo_route = _single_websocket_route("/echo/stream")
    assert echo_route.endpoint.__module__ == "main"
    assert echo_route.endpoint.__name__ == "echo_stream_ws"

    main_text = MAIN.read_text(encoding="utf-8")
    assert '@app.post("/voice/transcribe")' in main_text
    assert "VoiceTranscribeServiceDependencies" in main_text
    assert "run_voice_transcribe_service_body" in main_text
    assert "except AudioRuntimeHttpError as e:" in main_text


def _deps(*, exists=True, transcribed=None, calls=None):
    calls = calls if calls is not None else []
    transcribed = transcribed or {
        "text": "hello",
        "language": "en",
        "duration": 1.25,
        "model": "large-v3-turbo",
        "post_filter": {"enabled": True, "rejected": False, "reject_reason": "", "retry_applied": False},
        "metrics": {"segment_count": 1},
    }

    def transcribe_audio(audio, **kwargs):
        calls.append((audio, kwargs))
        return transcribed

    return audio_runtime.VoiceTranscribeServiceDependencies(
        apply_asr_runtime_settings=lambda req: calls.append(("settings", dict(req))) or {},
        resolve_asr_profile=lambda profile: "balanced" if str(profile or "").lower() not in {"fast", "quality"} else str(profile).lower(),
        voice_model_exists=lambda model: exists,
        transcribe_audio=transcribe_audio,
        is_runpod_runtime=lambda: False,
    )


def test_service_body_uses_dependency_injection_and_preserves_sse_result_shape():
    calls = []
    response = audio_runtime.run_voice_transcribe_service_body(
        {
            "audio_base64": base64.b64encode(b"audio-bytes").decode("ascii"),
            "language": "en",
            "model": "large-v3-turbo",
            "audio_format": "webm",
            "beam_size": "3",
            "best_of": "2",
        },
        _deps(exists=True, calls=calls),
    )

    assert isinstance(response, audio_runtime.VoiceTranscribeServiceResponse)
    assert response.media_type == "text/event-stream"
    assert dict(response.headers) == {"X-Accel-Buffering": "no", "Cache-Control": "no-cache"}
    events = list(response.body_iterator)
    assert len(events) == 2
    assert '"type": "transcribing"' in events[0]
    assert '"type": "result"' in events[1]
    assert '"text": "hello"' in events[1]
    assert '"language": "en"' in events[1]
    assert '"duration": 1.25' in events[1]

    audio, kwargs = calls[-1]
    assert audio == b"audio-bytes"
    assert kwargs["language"] == "en"
    assert kwargs["model_name"] == "large-v3-turbo"
    assert kwargs["auto_unload"] is False
    assert kwargs["audio_format"] == "webm"
    assert kwargs["asr_profile"] == "balanced"
    assert kwargs["beam_size"] == 3
    assert kwargs["best_of"] == 2


def test_service_body_preserves_download_and_stream_error_events():
    def fail_transcribe(*args, **kwargs):
        raise RuntimeError("boom")

    deps = _deps(exists=False)
    deps = audio_runtime.VoiceTranscribeServiceDependencies(
        apply_asr_runtime_settings=deps.apply_asr_runtime_settings,
        resolve_asr_profile=deps.resolve_asr_profile,
        voice_model_exists=deps.voice_model_exists,
        transcribe_audio=fail_transcribe,
        is_runpod_runtime=lambda: True,
    )
    response = audio_runtime.run_voice_transcribe_service_body(
        {"audio_base64": base64.b64encode(b"audio").decode("ascii")},
        deps,
    )
    events = list(response.body_iterator)
    assert '"type": "downloading"' in events[0]
    assert "RunPod" in events[0]
    assert '"type": "transcribing"' in events[1]
    assert '"type": "error"' in events[2]
    assert "voice transcribe failed: boom" in events[2]


def test_audio_runtime_http_error_mapping_inputs_are_unchanged():
    try:
        audio_runtime.run_voice_transcribe_service_body({}, _deps())
    except audio_runtime.AudioRuntimeHttpError as exc:
        assert exc.status_code == 400
        assert exc.detail == "audio_base64 required"
    else:
        raise AssertionError("expected AudioRuntimeHttpError")

    try:
        audio_runtime.run_voice_transcribe_service_body({"audio_base64": "!!!not-base64!!!"}, _deps())
    except audio_runtime.AudioRuntimeHttpError as exc:
        assert exc.status_code == 400
        assert str(exc.detail).startswith("invalid audio_base64:")
    else:
        raise AssertionError("expected AudioRuntimeHttpError")


def test_import_time_cuda_probe_is_not_added_by_audio_runtime_reload(monkeypatch):
    sentinel = SimpleNamespace(calls=0)

    def forbidden(*args, **kwargs):
        sentinel.calls += 1
        raise AssertionError("CUDA probe should not run while importing audio_runtime")

    monkeypatch.setattr(audio_runtime, "classify_voice_transcribe_failure", forbidden)
    importlib.reload(audio_runtime)
    assert sentinel.calls == 0
