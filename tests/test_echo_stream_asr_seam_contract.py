from pathlib import Path

import main
from app.services import audio_runtime


DOC = Path("docs/echo_stream_runtime_inventory.md")
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


def test_echo_stream_runtime_inventory_exists_and_freezes_high_risk_route_owner():
    assert DOC.exists()
    text = DOC.read_text(encoding="utf-8")

    for required in [
        "WebSocket `/echo/stream` is a high-risk route",
        "route owner is `main.py`",
        "echo_stream_ws",
        "_echo_voice_transcribe",
        "POST `/voice/transcribe` has its service body extracted",
        "websocket message shape must be maintained",
        "CUDA fallback / CPU fallback",
        "debug log format",
    ]:
        assert required in text


def test_audio_runtime_declares_echo_stream_asr_seam_types_and_helpers():
    for name in [
        "EchoStreamAsrInput",
        "EchoStreamAsrResult",
        "EchoStreamAsrDiagnostics",
        "EchoStreamAsrPlan",
        "build_echo_stream_asr_input",
        "summarize_echo_stream_asr_result",
        "normalize_echo_stream_asr_error",
    ]:
        assert hasattr(audio_runtime, name), name

    snapshot = audio_runtime.build_echo_stream_asr_input(
        audio_bytes=b"abc",
        seq=7,
        mime="audio/webm",
        session_id="s1",
        initial_prompt="hello",
    )
    assert isinstance(snapshot, audio_runtime.EchoStreamAsrInput)
    assert snapshot.audio_bytes_count == 3
    assert snapshot.seq == 7
    assert snapshot.session_id == "s1"
    assert snapshot.initial_prompt_present is True

    summary = audio_runtime.summarize_echo_stream_asr_result(
        {"text": " hi ", "language": "en", "duration": "1.5", "metrics": {"segment_count": 1}}
    )
    assert isinstance(summary, audio_runtime.EchoStreamAsrResult)
    assert summary.result_chars == 2
    assert summary.language == "en"
    assert summary.duration == 1.5

    error = audio_runtime.normalize_echo_stream_asr_error(
        RuntimeError("boom"), session_id="s1", seq=7, audio_bytes_count=3, mime="audio/webm"
    )
    assert error["websocket_error_payload"]["type"] == "error"
    assert error["websocket_error_payload"]["detail"] == "ASR error: boom"
    assert error["ui_log_payload"]["type"] == "ui_log"
    assert error["ack_error_payload"] == {"type": "ack", "seq": 7, "error": True}


def test_audio_runtime_echo_seam_remains_route_neutral_and_import_safe():
    text = SERVICE.read_text(encoding="utf-8")

    for forbidden in [
        "import main",
        "from main import",
        "APIRouter",
        "@router",
        "@app",
        "run_echo_stream_service_body",
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
    ]:
        assert forbidden not in top_level_imports


def test_echo_stream_and_voice_transcribe_route_owners_remain_main_py():
    echo_route = _single_websocket_route("/echo/stream")
    assert echo_route.endpoint.__module__ == "main"
    assert echo_route.endpoint.__name__ == "echo_stream_ws"

    transcribe_route = _single_http_route("/voice/transcribe", "POST")
    assert transcribe_route.endpoint.__module__ == "main"
    assert transcribe_route.endpoint.__name__ == "voice_transcribe_api"

    main_text = MAIN.read_text(encoding="utf-8")
    assert '@app.websocket("/echo/stream")' in main_text
    assert '@app.post("/voice/transcribe")' in main_text
    assert "PR4.63: Echo WebSocket high-risk route." in main_text
    assert "Route owner and websocket loop intentionally remain in main.py." in main_text
