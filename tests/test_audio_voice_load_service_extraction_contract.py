from pathlib import Path

import main
from app.services import audio_runtime


MAIN = Path("main.py")
SERVICE = Path("app/services/audio_runtime.py")
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


def test_voice_load_route_owner_remains_main_while_transcribe_is_extracted():
    route = _single_http_route("/voice/load", "POST")
    assert route.endpoint.__module__ == "main"
    assert route.endpoint.__name__ == "voice_load_api"

    transcribe_route = _single_http_route("/voice/transcribe", "POST")
    assert transcribe_route.endpoint.__module__ == "main"
    assert transcribe_route.endpoint.__name__ == "voice_transcribe_api"


def test_voice_load_inventory_stays_compatible_with_pr462_transcribe_extraction():
    service_text = SERVICE.read_text(encoding="utf-8")
    doc_text = REMAINING_DOC.read_text(encoding="utf-8")

    assert hasattr(audio_runtime, "run_voice_transcribe_service_body")
    assert "POST `/voice/load` は service body 抽出済み" in doc_text
    assert "`/voice/load` と `/voice/transcribe` は service body 抽出済み" in doc_text
    assert "import main" not in service_text
    assert "from main import" not in service_text
