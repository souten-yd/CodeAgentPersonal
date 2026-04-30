from app.tts.language_router import resolve_tts_language_route


def test_jp_extra_japanese_input_no_translation():
    req = {"text": "こんにちは", "echo_output_language": "ja", "echo_tts_language": "en"}
    route = resolve_tts_language_route(req, "2.0-JP-Extra")
    assert route["needs_translation"] is False
    assert route["normalizer"] == "sbv2_jp_extra"
    assert route["tts_language"] == "ja"


def test_jp_extra_english_input_translation_to_ja():
    req = {"text": "hello", "echo_output_language": "en", "echo_tts_language": "en"}
    route = resolve_tts_language_route(req, "2.0-jp-extra")
    assert route["needs_translation"] is True
    assert route["translation_target_language"] == "ja"


def test_global_source_en_tts_en_no_translation():
    route = resolve_tts_language_route({"text": "hello", "echo_output_language": "en", "echo_tts_language": "en"}, "global")
    assert route["needs_translation"] is False


def test_global_source_ja_tts_en_translation_to_en():
    route = resolve_tts_language_route({"text": "こんにちは", "echo_output_language": "ja", "echo_tts_language": "en"}, "global")
    assert route["needs_translation"] is True
    assert route["translation_target_language"] == "en"


def test_global_source_en_tts_ja_translation_to_ja():
    route = resolve_tts_language_route({"text": "hello", "echo_output_language": "en", "echo_tts_language": "ja"}, "global")
    assert route["needs_translation"] is True
    assert route["translation_target_language"] == "ja"


def test_same_as_asr_uses_asr_language():
    route = resolve_tts_language_route(
        {"text": "hello", "echo_output_language": "same_as_asr", "echo_asr_language": "en", "echo_tts_language": "ja"},
        "global",
    )
    assert route["source_language"] == "en"


def test_auto_bias_detection_ja_and_en():
    ja_route = resolve_tts_language_route({"text": "これはテスト", "echo_output_language": "auto", "echo_tts_language": "ja"}, "global")
    en_route = resolve_tts_language_route({"text": "this is a test", "echo_output_language": "auto", "echo_tts_language": "en"}, "global")
    assert ja_route["source_language"] == "ja"
    assert en_route["source_language"] == "en"
