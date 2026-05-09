import ast
from pathlib import Path

from fastapi.testclient import TestClient

import main
from app.server import create_app

AUDIO = Path("app/api/audio.py")
MAIN = Path("main.py")
SERVER = Path("app/server.py")


def _audio_text() -> str:
    assert AUDIO.exists(), "missing audio read/status router"
    return AUDIO.read_text(encoding="utf-8")


def _single_http_route(app, path: str, method: str):
    routes = [
        route
        for route in app.routes
        if getattr(route, "path", None) == path
        and method.upper() in getattr(route, "methods", set())
    ]
    assert len(routes) == 1, f"expected one {method} {path}, got {len(routes)}"
    return routes[0]


def _single_websocket_route(app, path: str):
    routes = [
        route
        for route in app.routes
        if getattr(route, "path", None) == path and not hasattr(route, "methods")
    ]
    assert len(routes) == 1, f"expected one websocket {path}, got {len(routes)}"
    return routes[0]


def test_audio_router_exists_and_is_import_safe():
    text = _audio_text()
    assert "APIRouter" in text
    assert "router = APIRouter()" in text
    assert "import main" not in text
    assert "from main import" not in text
    assert "detect_audio_runtime()" not in text
    assert "llm" not in text.lower() or "direct LLM fallback calls" in text

    tree = ast.parse(text)
    top_imports = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            top_imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            top_imports.append(node.module or "")
    forbidden = [
        "main",
        "torch",
        "ctranslate2",
        "faster_whisper",
        "app.tts.style_bert_vits2_runtime",
        "style_bert_vits2_runtime",
    ]
    for name in top_imports:
        assert all(fragment not in name for fragment in forbidden), name


def test_server_lazily_includes_audio_router():
    text = SERVER.read_text(encoding="utf-8")
    assert "from app.api.audio import router as audio_router" in text
    assert text.index("def include_routers") < text.index("from app.api.audio import router as audio_router")


def test_create_app_audio_fallbacks_are_side_effect_free_contracts():
    client = TestClient(create_app())

    voice = client.get("/voice/status")
    assert voice.status_code == 200
    assert voice.json() == {
        "ok": True,
        "status": "uninitialized",
        "device": None,
        "compute_type": None,
        "degraded": False,
        "reason": "provider unavailable",
    }

    asr = client.get("/asr/config")
    assert asr.status_code == 200
    assert asr.json() == {
        "ok": True,
        "available": False,
        "status": "unavailable",
        "provider": "unavailable",
    }

    debug = client.get("/audio/runtime/debug")
    assert debug.status_code == 200
    debug_payload = debug.json()
    assert debug_payload["audio_runtime"]["status"] == "unavailable"
    assert debug_payload["main_venv_cuda"]["available"] is False
    assert debug_payload["ctranslate2_cuda"]["available"] is False
    assert debug_payload["sbv2_venv_cuda_probe"]["available"] is False

    models = client.get("/api/tts/style-bert-vits2/models")
    assert models.status_code == 200
    assert models.json()["models"] == []
    assert models.json()["model_details"] == []

    preview = client.post(
        "/api/tts/style-bert-vits2/preview-normalization",
        json={"text": "hello", "language": "JP"},
    )
    assert preview.status_code == 200
    preview_payload = preview.json()
    assert preview_payload["normalized_text"] == "hello"
    assert preview_payload["reason"] == "provider unavailable"


def test_production_main_app_registers_audio_providers():
    state = main.app.state
    for provider_name in [
        "voice_status_provider",
        "asr_config_provider",
        "audio_runtime_debug_provider",
        "sbv2_models_provider",
        "sbv2_preview_normalization_provider",
    ]:
        assert callable(getattr(state, provider_name, None)), provider_name


def test_audio_read_routes_are_owned_by_audio_router_and_execution_stays_main():
    expected_audio = [
        ("/voice/status", "GET", "voice_status_api"),
        ("/asr/config", "GET", "asr_config_api"),
        ("/audio/runtime/debug", "GET", "get_audio_runtime_debug_api"),
        ("/api/tts/style-bert-vits2/models", "GET", "api_style_bert_vits2_models"),
        (
            "/api/tts/style-bert-vits2/preview-normalization",
            "POST",
            "api_style_bert_vits2_preview_normalization",
        ),
    ]
    for path, method, handler_name in expected_audio:
        route = _single_http_route(main.app, path, method)
        assert route.endpoint.__module__ == "app.api.audio"
        assert route.endpoint.__name__ == handler_name

    expected_main = [
        ("/voice/load", "POST", "voice_load_api"),
        ("/voice/transcribe", "POST", "voice_transcribe_api"),
        ("/tts/synthesize", "POST", "tts_synthesize_api"),
        ("/tts/synthesize-batch", "POST", "tts_synthesize_batch_api"),
        ("/api/tts/style-bert-vits2/prepare", "POST", "api_style_bert_vits2_prepare"),
    ]
    for path, method, handler_name in expected_main:
        route = _single_http_route(main.app, path, method)
        assert route.endpoint.__module__ == "main"
        assert route.endpoint.__name__ == handler_name

    ws = _single_websocket_route(main.app, "/echo/stream")
    assert ws.endpoint.__module__ == "main"
    assert ws.endpoint.__name__ == "echo_stream_ws"


def test_main_removed_audio_read_route_decorators_but_keeps_provider_payloads():
    text = MAIN.read_text(encoding="utf-8")
    for removed in [
        '@app.get("/voice/status")',
        '@app.get("/asr/config")',
        '@app.get("/audio/runtime/debug")',
        '@app.get("/api/tts/style-bert-vits2/models")',
        '@app.post("/api/tts/style-bert-vits2/preview-normalization")',
    ]:
        assert removed not in text
    for provider in [
        "def voice_status_payload",
        "def asr_config_payload",
        "def audio_runtime_debug_payload",
        "def sbv2_models_payload",
        "def sbv2_preview_normalization_payload",
    ]:
        assert provider in text
