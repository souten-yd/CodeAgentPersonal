from app.tts import text_normalizer
from app.tts.text_normalizer import normalize_text_for_sbv2_jp_extra, preprocess_text_for_tts


def _normalize(text: str) -> str:
    return normalize_text_for_sbv2_jp_extra(text, {})["normalized_text"]


def test_keeps_sentence_period_separator():
    out = _normalize("これはテストです。次に進みます。")
    assert "。" in out
    assert out == "これはテストです。次に進みます。"


def test_no_unnatural_sentence_joining():
    out = _normalize("これはテストです。次に進みます。")
    assert out != "これはテストです次に進みます"


def test_emoji_removed_with_sentence_pause_kept():
    out = _normalize("了解です😊。次に進みます。")
    assert "😊" not in out
    assert out == "了解です。次に進みます。"


def test_url_removed_without_breaking_sentence_boundary():
    out = _normalize("詳細は https://example.com を見てください。次に進みます。")
    assert "https://example.com" not in out
    assert "見てください。次に進みます。" in out


def test_repeated_punctuation_collapses_naturally():
    out = _normalize("これは、、、テストです。。。")
    assert out == "これは、テストです。"


def test_markdown_cleanup_heading_and_bullets():
    out = _normalize("# 見出し\n- 項目1\n- 項目2")
    assert "#" not in out
    assert "見出し" in out
    assert "・項目1" in out
    assert "・項目2" in out


def test_dictionary_katakana_python_fastapi():
    out = _normalize("PythonでFastAPIを使います。")
    assert "パイソン" in out
    assert "ファストエーピーアイ" in out


def test_dictionary_katakana_runpod_style_bert_vits2():
    out = _normalize("RunPod上でStyle-Bert-VITS2をロードします。")
    assert "ランポッド" in out
    assert "スタイルバートブイツーツー" in out


def test_dictionary_katakana_gpu_vram():
    out = _normalize("GPUとVRAMを確認します。")
    assert "ジーピーユー" in out
    assert "ブイラム" in out


def test_dictionary_katakana_github_docker():
    out = _normalize("GitHubからDockerで起動します。")
    assert "ギットハブ" in out
    assert "ドッカー" in out


def test_llm_failure_does_not_raise_and_records_warning(monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("llm offline")

    monkeypatch.setattr(text_normalizer, "katakanaize_english_segments_with_llm", _boom)
    result = normalize_text_for_sbv2_jp_extra("UnknownWordを読みます。", {})
    assert "UnknownWord" not in result["normalized_text"]
    assert any("english llm katakanaize failed" in w for w in result["warnings"])
    assert "english_spelling_fallback_applied" in result["warnings"]
    assert any(op.get("type") == "warning" and op.get("category") == "english_katakanaize" for op in result["operations"])


def test_no_notation_kept_readable():
    out = _normalize("No.1を確認します。")
    assert "ナンバー1" in out


def test_version_not_broken_by_period_normalization():
    out = _normalize("v1.2を使います。")
    assert "バージョン" in out
    assert "v1。2" not in out


def test_decimal_gb_not_broken():
    out = _normalize("3.5GBのVRAMです。")
    assert "ギガバイト" in out
    assert "3。5" not in out


def test_decimal_khz_not_broken():
    out = _normalize("10.5kHzで動作します。")
    assert "キロヘルツ" in out
    assert "10。5" not in out


def test_voltage_unit_readable():
    out = _normalize("1080Vです。")
    assert "ボルト" in out


def test_current_unit_readable():
    out = _normalize("1000Aです。")
    assert "アンペア" in out


def test_power_unit_readable():
    out = _normalize("500kWです。")
    assert "キロワット" in out


def test_period_kept_between_sentences():
    out = _normalize("これはテストです。次です。")
    assert out == "これはテストです。次です。"


def test_url_and_emoji_removal_do_not_join_sentences():
    out = _normalize("前です。https://example.com😊後です。")
    assert "前です。後です。" in out.replace(" ", "")


def test_echo_translation_japanese_tts_preprocess_removes_english():
    out = preprocess_text_for_tts("Echo VaultのUploadでPlaywrightを使います。", target_language="ja")
    assert "エコー" in out["text"]
    assert "ボルト" in out["text"]
    assert "アップロード" in out["text"]
    assert "プレイライト" in out["text"]
    assert not any(ch.isascii() and ch.isalpha() for ch in out["text"])


def test_fallback_unknown_term_is_katakana_only():
    result = normalize_text_for_sbv2_jp_extra("UnknownTerm", {})
    text = result["normalized_text"]
    assert text
    assert not any(ch.isascii() and ch.isalpha() for ch in text)
    assert not any("Ａ" <= ch <= "Ｚ" or "ａ" <= ch <= "ｚ" for ch in text)


def test_fallback_abc_to_spelling_reading():
    assert text_normalizer._fallback_spelling_reading("ABC") == "エービーシー"


def test_dictionary_ui_and_vad_priority():
    out = _normalize("UIとVADを確認します。")
    assert "ユーアイ" in out
    assert "ブイエーディー" in out


def test_echo_vault_unknown_term_has_no_english_left():
    out = preprocess_text_for_tts("Echo VaultでUnknownTermを使います。", target_language="ja")
    assert "エコー" in out["text"]
    assert "ボルト" in out["text"]
    assert not any(ch.isascii() and ch.isalpha() for ch in out["text"])
    assert not any("Ａ" <= ch <= "Ｚ" or "ａ" <= ch <= "ｚ" for ch in out["text"])


def test_fallback_spelling_reading_directml_has_no_english():
    out = text_normalizer._fallback_spelling_reading("DirectML")
    assert out
    assert not any(ch.isascii() and ch.isalpha() for ch in out)
    assert not any("Ａ" <= ch <= "Ｚ" or "ａ" <= ch <= "ｚ" for ch in out)
