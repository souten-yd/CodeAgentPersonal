from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_PATHS = [
    ROOT / "ui.html",
    ROOT / "web" / "feature_manifest.json",
    ROOT / "web" / "js" / "echo_api.js",
    ROOT / "web" / "js" / "echo_stream.js",
    ROOT / "web" / "js" / "echo_ui.js",
]


def read_all() -> str:
    parts = []
    for path in TEXT_PATHS:
        if path.exists():
            parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def test_echo_tts_is_sbv2_only_no_qwen_tokens_in_echo_modules():
    text = read_all().lower()
    forbidden = [
        "qwen",
        "qwen3",
        "qwen3model",
        "_clearqwen3clonestatustimer",
        "_setqwen3cloneplaytoggle",
    ]
    for token in forbidden:
        assert token not in text


def test_legacy_qwen_storage_keys_are_not_declared_or_read_as_options():
    text = read_all()
    forbidden = [
        "tts_qwen3model",
        "tsasr_qwen3model",
        "echo_qwen3model",
    ]
    for token in forbidden:
        assert token not in text


def test_default_tts_engine_is_style_bert_vits2():
    text = read_all()
    assert "style_bert_vits2" in text


def test_default_sbv2_model_is_koharune_ami():
    text = read_all()
    assert "koharune-ami" in text
    assert "jvnv-F1-jp" not in text


def test_feature_manifest_echo_storage_keys_are_sbv2_only():
    manifest = (ROOT / "web" / "feature_manifest.json").read_text(encoding="utf-8")
    assert "echo_style_bert_vits2_model" in manifest
    assert "tts_style_bert_vits2_model" in manifest
    assert "qwen" not in manifest.lower()
    assert "tts_qwen3model" not in manifest
    assert "tsasr_qwen3model" not in manifest
    assert "echo_qwen3model" not in manifest
    assert "tts_engine" not in manifest
    assert "echo_tts_engine" not in manifest
