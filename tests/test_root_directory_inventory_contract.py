import json
from pathlib import Path

import main


DOC = Path("docs/root_directory_inventory.md")
JSON_DOC = Path("docs/generated/root_directory_inventory.json")
EXPECTED_ROOT_FILES = {
    ".dockerignore",
    ".gitignore",
    "DLllama.bat",
    "Dockerfile",
    "README.md",
    "agent_runtime.py",
    "benchmark_mem.py",
    "main.py",
    "requirements-tts.txt",
    "requirements.txt",
    "setup_style_bert_vits2_windows.bat",
    "setup_whisper_cpp_vulkan_windows.bat",
    "start.bat",
    "ui.html",
}


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


def test_root_directory_inventory_docs_and_generated_json_exist():
    assert DOC.exists()
    assert DOC.read_text(encoding="utf-8").strip()
    assert JSON_DOC.exists()
    assert _inventory_json()["generated_by"] == "scripts/inventory_root_files.py"


def test_root_keep_files_and_required_manifests_are_documented():
    text = DOC.read_text(encoding="utf-8")

    for required in [
        "`main.py`",
        "`Dockerfile`",
        "`requirements*.txt`",
        "`requirements.txt`",
        "`requirements-tts.txt`",
        "`pyproject.toml`",
        "`README.md`",
        "`.gitignore`",
        "`.dockerignore`",
    ]:
        assert required in text

    assert "Keep in root" in text
    assert "Do not move" in text


def test_move_candidate_categories_are_documented():
    text = DOC.read_text(encoding="utf-8")

    for category in [
        "`scripts/`",
        "`tools/`",
        "`docs/runbooks/`",
        "`docs/refactor/`",
        "`tests/`",
    ]:
        assert category in text

    for pattern in ["`check_*.py`", "`export_*.py`", "`collect_*.py`", "`diagnose_*.py`", "`verify_*.py`"]:
        assert pattern in text


def test_pr465_does_not_move_current_root_files():
    current_root_files = {path.name for path in Path(".").iterdir() if path.is_file()}
    assert EXPECTED_ROOT_FILES <= current_root_files

    inventory_names = {record["name"] for record in _inventory_json()["files"]}
    assert EXPECTED_ROOT_FILES <= inventory_names


def test_generated_inventory_records_classification_and_references():
    inventory = _inventory_json()
    by_name = {record["name"]: record for record in inventory["files"]}

    assert by_name["main.py"]["category"] == "root-keep"
    assert by_name["main.py"]["move_candidate"] is False
    assert by_name["Dockerfile"]["category"] == "root-keep"
    assert by_name["requirements.txt"]["category"] == "root-keep"
    assert by_name["README.md"]["category"] == "root-keep"
    assert by_name["agent_runtime.py"]["category"] == "needs-investigation"
    assert by_name["benchmark_mem.py"]["suggested_destination"] == "tools/"
    assert ".github/workflows/runpod-test.yml" in by_name["benchmark_mem.py"]["references"]


def test_reference_source_check_policy_is_documented():
    text = DOC.read_text(encoding="utf-8")

    for source in [
        "`Dockerfile`",
        "`.github/workflows/*`",
        "`scripts/*`",
        "`app/*`",
        "`main.py`",
        "`README.md`",
        "`docs/*`",
        "`tests/*`",
    ]:
        assert source in text

    for check in ["GitHub Actions", "Docker", "Runpod", "app runtime", "contract test"]:
        assert check in text


def test_websocket_echo_stream_and_audio_runtime_ownership_are_untouched():
    doc_text = DOC.read_text(encoding="utf-8")
    remaining_text = Path("docs/refactor_remaining_main_routes_inventory.md").read_text(encoding="utf-8")

    assert "PR4.65 does not touch WebSocket `/echo/stream`" in doc_text
    assert "Audio/Echo runtime route ownership" in doc_text
    assert "WebSocket `/echo/stream` route移動はまだ保留" in remaining_text

    websocket_route = _single_websocket_route("/echo/stream")
    assert websocket_route.endpoint.__module__ == "main"
    assert websocket_route.endpoint.__name__ == "echo_stream_ws"

    for path, method, handler_name in [
        ("/voice/transcribe", "POST", "voice_transcribe_api"),
        ("/tts/synthesize", "POST", "tts_synthesize_api"),
        ("/tts/synthesize-batch", "POST", "tts_synthesize_batch_api"),
        ("/echo/sessions/{filename:path}", "DELETE", "echo_delete_session"),
    ]:
        route = _single_route(path, method)
        assert route.endpoint.__module__ == "main"
        assert route.endpoint.__name__ == handler_name
