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


FORBIDDEN_TTS_QWEN_TOKENS = [
    "_clearqwen3clonestatustimer",
    "_setqwen3cloneplaytoggle",
]

CLEANUP_ONLY_TOKENS = [
    "tts_qwen3model",
    "tsasr_qwen3model",
    "echo_qwen3model",
    "qwen3_ref_text",
    "qwen3_clone_require_ref_text",
    "qwen3_clone_test_text",
]


def assert_token_only_in_cleanup(text: str, token: str) -> None:
    start = 0
    while True:
      idx = text.find(token, start)
      if idx < 0:
          return
      window = text[max(0, idx - 300): idx + 300]
      assert "cleanupDeprecatedLegacyTtsStorage" in window or "removeItem" in window
      start = idx + len(token)


def test_echo_tts_is_sbv2_only_excluding_general_qwen_ui_tokens():
    text = read_all().lower()
    for token in FORBIDDEN_TTS_QWEN_TOKENS:
        assert token not in text


def test_legacy_qwen_storage_keys_are_cleanup_only():
    text = read_all()
    for token in CLEANUP_ONLY_TOKENS:
        assert token in text
        assert_token_only_in_cleanup(text, token)


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
