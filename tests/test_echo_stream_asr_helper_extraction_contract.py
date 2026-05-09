from pathlib import Path

import main
from app.services import audio_runtime

SERVICE = Path("app/services/audio_runtime.py")
MAIN = Path("main.py")
DOCS = [
    Path("docs/echo_stream_runtime_inventory.md"),
    Path("docs/echo_audio_runtime_inventory.md"),
    Path("docs/refactor_remaining_main_routes_inventory.md"),
    Path("docs/refactor_recovery_map.md"),
    Path("docs/api_route_ownership_inventory.md"),
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


def test_audio_runtime_declares_echo_stream_asr_service_extraction_contract():
    for name in [
        "EchoStreamAsrServiceDependencies",
        "EchoStreamAsrServiceResponse",
        "run_echo_stream_asr_service_body",
    ]:
        assert hasattr(audio_runtime, name), name


def test_audio_runtime_echo_stream_asr_service_remains_route_neutral_and_import_safe():
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


def test_echo_stream_and_voice_route_owners_remain_main_py():
    echo_route = _single_websocket_route("/echo/stream")
    assert echo_route.endpoint.__module__ == "main"
    assert echo_route.endpoint.__name__ == "echo_stream_ws"

    transcribe_route = _single_http_route("/voice/transcribe", "POST")
    assert transcribe_route.endpoint.__module__ == "main"
    assert transcribe_route.endpoint.__name__ == "voice_transcribe_api"

    load_route = _single_http_route("/voice/load", "POST")
    assert load_route.endpoint.__module__ == "main"
    assert load_route.endpoint.__name__ == "voice_load_api"


def test_echo_voice_transcribe_remains_thin_wrapper_calling_service_helper():
    main_text = MAIN.read_text(encoding="utf-8")
    assert "def _echo_voice_transcribe(" in main_text
    assert "async def echo_stream_ws" in main_text
    wrapper_start = main_text.index("def _echo_voice_transcribe(")
    wrapper_end = main_text.index("\ndef _echo_normalize_lang", wrapper_start)
    wrapper = main_text[wrapper_start:wrapper_end]
    assert "EchoStreamAsrServiceDependencies" in wrapper
    assert "run_echo_stream_asr_service_body" in wrapper
    assert "_voice_model.transcribe" in wrapper
    assert wrapper.count("_voice_model.transcribe") == 1
    assert "tempfile.NamedTemporaryFile" not in wrapper
    assert "_detect_repetition_loop" in wrapper


def test_docs_capture_pr464_message_shape_and_session_write_guardrails():
    combined = "\n".join(doc.read_text(encoding="utf-8") for doc in DOCS)
    for required in [
        "PR4.64 extracts the Echo stream ASR helper body",
        "WebSocket `/echo/stream` route owner remains `main.py`",
        "`echo_stream_ws` main loop remains in `main.py`",
        "_echo_voice_transcribe(...)` remains in `main.py` as a thin wrapper",
        "WebSocket message shape must not change",
        "Echo session write/save/delete behavior is not moved",
        "Echo WebSocket loop",
        "Echo session write/save",
        "Echo TTS chain",
    ]:
        assert required in combined
