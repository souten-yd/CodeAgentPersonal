import json
from pathlib import Path

import main
from scripts.inventory_root_files import build_inventory

DOC = Path("docs/root_directory_inventory.md")
JSON_DOC = Path("docs/generated/root_directory_inventory.json")

MOVED_FILES = {
    "agent_runtime.py": "tools/agent_runtime.py",
    "DLllama.bat": "tools/DLllama.bat",
}
ROOT_KEEP_FILES = [
    "main.py",
    "Dockerfile",
    "README.md",
    "requirements.txt",
    "requirements-tts.txt",
]
OPTIONAL_ROOT_KEEP_FILES = ["pyproject.toml", "LICENSE", "docker-compose.yml"]


def _single_route(path: str, method: str):
    matches = []
    for route in main.app.routes:
        if getattr(route, "path", None) != path:
            continue
        methods = getattr(route, "methods", set()) or set()
        if method in methods:
            matches.append(route)
    assert len(matches) == 1, f"expected one {method} {path}, got {len(matches)}"
    return matches[0]


def _single_websocket_route(path: str):
    matches = [route for route in main.app.routes if getattr(route, "path", None) == path]
    matches = [route for route in matches if "WebSocket" in route.__class__.__name__]
    assert len(matches) == 1, f"expected one websocket {path}, got {len(matches)}"
    return matches[0]


def _inventory_json() -> dict:
    return json.loads(JSON_DOC.read_text(encoding="utf-8"))


def test_pr466_moved_files_left_root_and_exist_in_tools():
    for original, current in MOVED_FILES.items():
        assert not Path(original).exists(), f"{original} must not remain at repository root"
        assert Path(current).exists(), f"{current} must exist after the low-risk move"


def test_pr466_inventory_doc_lists_each_move_source_and_destination():
    text = DOC.read_text(encoding="utf-8")

    assert "PR4.66 moved files" in text
    for original, current in MOVED_FILES.items():
        assert f"`{original}` -> `{current}`" in text


def test_pr466_generated_inventory_is_current_and_records_moved_files():
    inventory = _inventory_json()
    current_inventory = build_inventory()
    assert inventory == current_inventory

    root_names = {record["name"] for record in inventory["files"]}
    moved = {record["original_path"]: record["current_path"] for record in inventory["moved_files"]}

    assert not set(MOVED_FILES).intersection(root_names)
    assert moved == MOVED_FILES
    assert len(inventory["files"]) == len([path for path in Path(".").iterdir() if path.is_file()])


def test_pr466_root_keep_files_remain_in_root():
    for filename in ROOT_KEEP_FILES:
        assert Path(filename).is_file(), f"{filename} must remain at repository root"

    for filename in OPTIONAL_ROOT_KEEP_FILES:
        if Path(filename).exists():
            assert Path(filename).is_file(), f"{filename} must remain a root file when present"


def test_pr466_echo_stream_and_audio_runtime_route_ownership_are_unchanged():
    websocket_route = _single_websocket_route("/echo/stream")
    assert websocket_route.endpoint.__module__ == "main"
    assert websocket_route.endpoint.__name__ == "echo_stream_ws"

    for path, method, handler_name in [
        ("/voice/load", "POST", "voice_load_api"),
        ("/voice/transcribe", "POST", "voice_transcribe_api"),
        ("/tts/synthesize", "POST", "tts_synthesize_api"),
        ("/tts/synthesize-batch", "POST", "tts_synthesize_batch_api"),
        ("/echo/sessions/{filename:path}", "DELETE", "echo_delete_session"),
        ("/api/tts/style-bert-vits2/prepare", "POST", "api_style_bert_vits2_prepare"),
    ]:
        route = _single_route(path, method)
        assert route.endpoint.__module__ == "main"
        assert route.endpoint.__name__ == handler_name
