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
