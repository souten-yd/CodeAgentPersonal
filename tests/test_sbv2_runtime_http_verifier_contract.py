from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_sbv2_runtime_http.py"


def test_sbv2_http_verifier_exists():
    assert SCRIPT.exists()


def test_sbv2_http_verifier_uses_standard_library_only():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "urllib.request" in source
    assert "import requests" not in source
    assert "from requests" not in source


def test_sbv2_http_verifier_checks_expected_endpoints():
    source = SCRIPT.read_text(encoding="utf-8")
    expected = [
        "/audio/runtime/debug",
        "/api/tts/style-bert-vits2/prepare",
        "/tts/synthesize",
    ]
    for token in expected:
        assert token in source


def test_sbv2_http_verifier_defaults_are_sbv2_only():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "koharune-ami" in source
    assert "style_bert_vits2" in source
    forbidden = [
        "qwen3",
        "qwen3model",
        "tts_qwen3model",
        "tsasr_qwen3model",
        "echo_qwen3model",
    ]
    lowered = source.lower()
    for token in forbidden:
        assert token not in lowered


def test_sbv2_http_verifier_does_not_import_runtime_or_heavy_modules():
    source = SCRIPT.read_text(encoding="utf-8").lower()
    forbidden = [
        "import torch",
        "import onnxruntime",
        "style_bert_vits2_runtime",
        "subprocess",
        "download",
        "load_model",
    ]
    for token in forbidden:
        assert token not in source


def test_sbv2_http_verifier_can_write_report_and_has_exit_semantics():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "--out" in source
    assert "return 0 if report" in source
