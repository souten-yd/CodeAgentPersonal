from pathlib import Path

import main
from app.services import audio_runtime


DOC = Path("docs/asr_transcribe_runtime_inventory.md")
SERVICE = Path("app/services/audio_runtime.py")
MAIN = Path("main.py")
REMAINING_DOC = Path("docs/refactor_remaining_main_routes_inventory.md")


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


def test_asr_transcribe_runtime_inventory_doc_exists_and_freezes_high_risk_route():
    assert DOC.exists()
    text = DOC.read_text(encoding="utf-8")

    for required in [
        "POST /voice/transcribe",
        "high-risk execution route",
        "route owner in `main.py`",
        "service body into `app/services/audio_runtime.py`",
        "CUDA fallback",
        "cpu-int8 fallback",
        "degraded reason",
        "audio_base64",
        "temporary file",
        "faster-whisper",
        "response payload",
        "error payload",
        "WebSocket `/echo/stream`",
    ]:
        assert required in text


def test_audio_runtime_declares_transcribe_service_types():
    for name in [
        "VoiceTranscribeInput",
        "VoiceTranscribeResult",
        "VoiceTranscribeDiagnostics",
        "VoiceTranscribeServicePlan",
        "VoiceTranscribeServiceDependencies",
        "VoiceTranscribeServiceResponse",
        "run_voice_transcribe_service_body",
        "normalize_voice_transcribe_error",
        "summarize_voice_transcribe_result",
        "classify_voice_transcribe_failure",
    ]:
        assert hasattr(audio_runtime, name), name


def test_audio_runtime_transcribe_seam_remains_route_neutral_and_import_safe():
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
    ]:
        assert forbidden not in top_level_imports


def test_voice_transcribe_and_echo_stream_route_owners_remain_main_py():
    transcribe_route = _single_http_route("/voice/transcribe", "POST")
    assert transcribe_route.endpoint.__module__ == "main"
    assert transcribe_route.endpoint.__name__ == "voice_transcribe_api"

    echo_route = _single_websocket_route("/echo/stream")
    assert echo_route.endpoint.__module__ == "main"
    assert echo_route.endpoint.__name__ == "echo_stream_ws"


def test_main_py_contains_pr462_transcribe_service_comment():
    text = MAIN.read_text(encoding="utf-8")
    assert "PR4.62: ASR transcribe service body extracted; route owner remains main.py." in text
    assert "Preserve CUDA fallback, response shape, model load timing, and debug entry format." in text
    assert "VoiceTranscribeServiceDependencies" in text
    assert "run_voice_transcribe_service_body" in text


def test_remaining_routes_doc_records_voice_load_extracted_and_next_sequence():
    text = REMAINING_DOC.read_text(encoding="utf-8")

    for required in [
        "POST `/voice/load` は service body 抽出済み",
        "POST `/voice/transcribe` は service body 抽出済み",
        "WebSocket `/echo/stream` は `main.py` に残留",
        "PR4.62 で POST `/voice/transcribe` の service body",
        "PR4.63: Stabilize Echo stream ASR reuse seam",
        "PR4.64+: Echo WebSocket extraction last",
    ]:
        assert required in text
