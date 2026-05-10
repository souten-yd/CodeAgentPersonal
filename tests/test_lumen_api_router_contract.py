from pathlib import Path

import main

LUMEN_API_PATH = Path("app/api/lumen.py")
ROUTE_DOC_PATH = Path("docs/api_route_ownership_inventory.md")


def _route(path: str, method: str):
    matches = [
        route
        for route in main.app.routes
        if getattr(route, "path", None) == path and method in getattr(route, "methods", set())
    ]
    assert len(matches) == 1
    return matches[0]


def test_lumen_api_router_exists_and_owns_routes():
    assert LUMEN_API_PATH.exists()
    assert _route("/lumen/submit", "POST").endpoint.__module__ == "app.api.lumen"
    assert _route("/lumen/tools/status", "GET").endpoint.__module__ == "app.api.lumen"
    assert _route("/lumen/tools/weather", "POST").endpoint.__module__ == "app.api.lumen"
    assert _route("/lumen/tools/news", "POST").endpoint.__module__ == "app.api.lumen"


def test_lumen_api_router_avoids_main_and_heavy_import_time_runtime():
    text = LUMEN_API_PATH.read_text(encoding="utf-8")
    assert "import main" not in text
    assert "from main import" not in text
    for forbidden in ["app.asr", "app.tts", "style_bert", "WHISPER", "cuda", "runpod"]:
        assert forbidden not in text


def test_route_owner_docs_include_lumen_routes():
    text = ROUTE_DOC_PATH.read_text(encoding="utf-8")
    assert "/lumen/submit" in text
    assert "/lumen/tools/status" in text
    assert "/lumen/tools/weather" in text
    assert "/lumen/tools/news" in text
    assert "app/api/lumen.py" in text
