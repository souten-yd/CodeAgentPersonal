from app.tts import text_normalizer
from app.tts.text_normalizer import normalize_text_for_sbv2_jp_extra


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
    assert "UnknownWord" in result["normalized_text"]
    assert any("english llm katakanaize failed" in w for w in result["warnings"])
    assert any(op.get("type") == "warning" and op.get("category") == "english_katakanaize" for op in result["operations"])
