from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "ui_module_ownership.md"


def test_ui_module_ownership_doc_exists():
    assert DOC.exists()


def test_ui_module_ownership_doc_mentions_core_modules():
    text = DOC.read_text(encoding="utf-8")
    required = [
        "ui.html",
        "web/js/atlas_api.js",
        "web/js/atlas_state.js",
        "web/js/atlas_ui.js",
        "web/js/echo_api.js",
        "web/js/echo_stream.js",
        "web/js/echo_ui.js",
        "web/js/runtime_diagnostics.js",
        "web/feature_manifest.json",
    ]
    for token in required:
        assert token in text


def test_ui_module_ownership_doc_lists_guardrails():
    text = DOC.read_text(encoding="utf-8")
    required = [
        "DOM rendering",
        "localStorage",
        "WebSocket",
        "MediaRecorder",
        "secret masking",
        "approval",
        "auto execute",
        "heavy probes",
    ]
    for token in required:
        assert token in text
