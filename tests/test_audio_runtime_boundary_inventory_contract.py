from pathlib import Path
import re

import main


DOC = Path("docs/echo_audio_runtime_inventory.md")
SERVICE = Path("app/services/audio_runtime.py")
MAIN = Path("main.py")


def _doc_text() -> str:
    assert DOC.exists(), "missing audio runtime inventory doc"
    return DOC.read_text(encoding="utf-8")


def _service_text() -> str:
    assert SERVICE.exists(), "missing route-neutral audio runtime service seam"
    return SERVICE.read_text(encoding="utf-8")


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


def _assert_main_owner(path: str, method: str, handler_name: str):
    route = _single_http_route(path, method)
    assert route.endpoint.__module__ == "main"
    assert route.endpoint.__name__ == handler_name


def test_audio_runtime_inventory_doc_exists_and_records_v28_baseline():
    text = _doc_text()
    assert "KasaneCore_v2.8" in text
    assert "e94c20dfe0d23e233f4dbc817af994408e739b80" in text
    assert "LLM / ASR / TTS / Nexus / Lumen" in text
    assert "ASR OK" in text
    assert "TTS/SBV2 OK" in text


def test_audio_runtime_inventory_risk_classification_for_target_endpoints():
    text = _doc_text()

    high_risk_patterns = [
        r"high-risk[^\n|]*\| WebSocket `/echo/stream`",
        r"high-risk[^\n|]*\| POST `/voice/transcribe`",
        r"high-risk[^\n|]*\| POST `/tts/synthesize`",
        r"high-risk[^\n|]*\| POST `/tts/synthesize-batch`",
    ]
    for pattern in high_risk_patterns:
        assert re.search(pattern, text), pattern

    low_or_medium_patterns = [
        r"low-risk[^\n|]*\| GET `/voice/status`",
        r"low-risk[^\n|]*\| GET `/asr/config`",
    ]
    for pattern in low_or_medium_patterns:
        assert re.search(pattern, text), pattern

    for required in [
        "POST `/voice/load`",
        "POST `/api/tts/style-bert-vits2/prepare`",
        "GET `/api/tts/style-bert-vits2/models`",
        "POST `/api/tts/style-bert-vits2/preview-normalization`",
        "DELETE `/echo/sessions/{filename:path}`",
        "runtime load",
        "CUDA probe",
        "Filesystem write",
        "LLM fallback",
        "create_app() fallback",
    ]:
        assert required in text


def test_audio_runtime_service_is_route_neutral_and_import_safe():
    text = _service_text()

    assert "AUDIO_RUNTIME_ENDPOINT_OWNERSHIP" in text
    assert "AudioRuntimeStatus" in text
    assert "AudioRuntimeDiagnostics" in text
    assert "normalize_audio_runtime_status_payload" in text
    assert "build_audio_runtime_debug_payload" in text
    assert "classify_audio_endpoint_risk" in text

    forbidden_fragments = [
        "import main",
        "from main import",
        "APIRouter",
        "@router",
        "@app",
    ]
    for fragment in forbidden_fragments:
        assert fragment not in text

    top_level_imports = "\n".join(line for line in text.splitlines() if line.startswith(("import ", "from ")))
    forbidden_top_level_imports = [
        "import torch",
        "from torch",
        "import ctranslate2",
        "from ctranslate2",
        "import faster_whisper",
        "from faster_whisper",
        "style_bert_vits2_runtime",
        "StyleBertVITS2Runtime",
    ]
    for fragment in forbidden_top_level_imports:
        assert fragment not in top_level_imports

    assert "detect_audio_runtime()" not in text
    assert "voice_load(" not in text
    assert "voice_transcribe" not in text


def test_main_audio_runtime_endpoint_owners_remain_main_py():
    _assert_main_owner("/voice/status", "GET", "voice_status_api")
    _assert_main_owner("/voice/load", "POST", "voice_load_api")
    _assert_main_owner("/voice/transcribe", "POST", "voice_transcribe_api")
    _assert_main_owner("/asr/config", "GET", "asr_config_api")
    _assert_main_owner("/tts/synthesize", "POST", "tts_synthesize_api")
    _assert_main_owner("/tts/synthesize-batch", "POST", "tts_synthesize_batch_api")
    _assert_main_owner("/api/tts/style-bert-vits2/prepare", "POST", "api_style_bert_vits2_prepare")
    _assert_main_owner("/api/tts/style-bert-vits2/models", "GET", "api_style_bert_vits2_models")
    _assert_main_owner(
        "/api/tts/style-bert-vits2/preview-normalization",
        "POST",
        "api_style_bert_vits2_preview_normalization",
    )
    _assert_main_owner("/echo/sessions/{filename:path}", "DELETE", "echo_delete_session")

    route = _single_websocket_route("/echo/stream")
    assert route.endpoint.__module__ == "main"
    assert route.endpoint.__name__ == "echo_stream_ws"


def test_main_py_has_pr454_inventory_comments_near_audio_runtime_routes():
    text = MAIN.read_text(encoding="utf-8")
    for route_literal in [
        '@app.get("/voice/status")',
        '@app.post("/voice/load")',
        '@app.post("/voice/transcribe")',
        '@app.websocket("/echo/stream")',
        '@app.delete("/echo/sessions/{filename:path}")',
        '@app.post("/api/tts/style-bert-vits2/prepare")',
        '@app.get("/api/tts/style-bert-vits2/models")',
        '@app.post("/api/tts/style-bert-vits2/preview-normalization")',
        '@app.post("/tts/synthesize")',
        '@app.post("/tts/synthesize-batch")',
        '@app.get("/asr/config")',
    ]:
        index = text.index(route_literal)
        window = text[max(0, index - 220):index]
        assert "PR4.54" in window
