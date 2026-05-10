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


def test_audio_runtime_declares_echo_session_write_service_contract():
    for name in [
        "EchoSessionWriteInput",
        "EchoSessionWriteResult",
        "EchoSessionWriteDiagnostics",
        "EchoSessionWriteServiceDependencies",
        "run_echo_session_write_service_body",
    ]:
        assert hasattr(audio_runtime, name), name


def test_audio_runtime_echo_session_write_service_remains_route_neutral_and_import_safe():
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


def test_echo_stream_and_read_only_route_ownership_remains_unchanged():
    echo_route = _single_websocket_route("/echo/stream")
    assert echo_route.endpoint.__module__ == "main"
    assert echo_route.endpoint.__name__ == "echo_stream_ws"

    sessions_route = _single_http_route("/echo/sessions", "GET")
    assert sessions_route.endpoint.__module__ == "app.api.echo"
    assert sessions_route.endpoint.__name__ == "get_echo_sessions_api"

    save_status_route = _single_http_route("/echo/save-status", "GET")
    assert save_status_route.endpoint.__module__ == "app.api.echo"
    assert save_status_route.endpoint.__name__ == "get_echo_save_status_api"


def test_main_keeps_websocket_loop_and_thin_session_write_wrapper():
    main_text = MAIN.read_text(encoding="utf-8")
    assert '@app.websocket("/echo/stream")' in main_text
    assert "async def echo_stream_ws" in main_text
    assert "def _echovault_save_session" in main_text
    assert "EchoSessionWriteServiceDependencies" in main_text
    assert "run_echo_session_write_service_body" in main_text

    wrapper_start = main_text.index("def _echovault_save_session")
    wrapper_end = main_text.index("\ndef _echo_schedule_session_save", wrapper_start)
    wrapper = main_text[wrapper_start:wrapper_end]
    assert "run_echo_session_write_service_body" in wrapper
    assert "with open(" not in wrapper
    assert "_echo_generate_minutes(session)" not in wrapper


def test_docs_capture_pr467_message_shape_and_session_storage_guardrails():
    combined = "\n".join(doc.read_text(encoding="utf-8") for doc in DOCS)
    for required in [
        "PR4.67 extracts the Echo session write/save helper body",
        "WebSocket `/echo/stream` route owner remains `main.py`",
        "`echo_stream_ws` main loop remains in `main.py`",
        "Echo ASR helper and session write/save helper bodies are extracted",
        "WebSocket message shape must not change",
        "Echo session save destination and filename format must not change",
        "Echo TTS chain",
        "Echo WebSocket loop",
        "WebSocket route extraction",
    ]:
        assert required in combined
