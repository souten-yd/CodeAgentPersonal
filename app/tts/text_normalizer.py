from __future__ import annotations

import re
import unicodedata
from typing import Any

from .katakanaizer import katakanaize_english_segments_with_llm

_JP_TEXT_PATTERN = re.compile(r"[ぁ-ゟ゠-ヿ㐀-䶿一-鿿々〆〤ｦ-ﾟ]")
_URL_PATTERN = re.compile(r"https?://[^\s]+|www\.[^\s]+", re.IGNORECASE)
_EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_EMOJI_PATTERN = re.compile(
    "[\U0001F300-\U0001F5FF\U0001F600-\U0001F64F\U0001F680-\U0001F6FF\U0001F900-\U0001F9FF\U0001FA70-\U0001FAFF]+"
)
_ASCII_WORD_PATTERN = re.compile(r"\b[A-Za-z][A-Za-z0-9_\-]*\b")
_CONTROL_PATTERN = re.compile(r"[\x00-\x08\x0B-\x1F\x7F]")
_MULTISPACE_PATTERN = re.compile(r"[ \t\u3000]+")
_NUMBER_UNIT_PATTERN = re.compile(
    r"(?P<number>\d+(?:[.,]\d+)?)\s*(?P<unit>tb|gb|mb|kb|vram|ghz|mhz|khz|km|kg|cm|mm|m|g|mg|ml|l|℃|°C|%|円|¥|\$)\b",
    re.IGNORECASE,
)
_CURRENCY_PREFIX_PATTERN = re.compile(r"(?P<currency>[$¥])\s*(?P<number>\d+(?:[.,]\d+)?)")
_NO_PATTERN = re.compile(r"\bNo\.\s*(?P<number>\d+)\b", re.IGNORECASE)
_VERSION_PATTERN = re.compile(r"\bv(?P<version>\d+(?:\.\d+)+)\b", re.IGNORECASE)

_DEFAULT_ENGLISH_DICT = {
    "ai": "エーアイ",
    "api": "エーピーアイ",
    "cpu": "シーピーユー",
    "gpu": "ジーピーユー",
    "openai": "オープンエーアイ",
    "chatgpt": "チャットジーピーティー",
    "llm": "エルエルエム",
    "asr": "エーエスアール",
    "tts": "ティーティーエス",
    "url": "ユーアールエル",
    "docker": "ドッカー",
    "github": "ギットハブ",
    "kasanecore": "カサネコア",
    "style-bert-vits2": "スタイルバートブイツーツー",
    "jp-extra": "ジェーピーエクストラ",
    "vram": "ブイラム",
    "ok": "オーケー",
    "ng": "エヌジー",
}
_UNIT_READABLE_MAP = {
    "tb": "テラバイト",
    "gb": "ギガバイト",
    "mb": "メガバイト",
    "kb": "キロバイト",
    "vram": "ブイラム",
    "ghz": "ギガヘルツ",
    "mhz": "メガヘルツ",
    "khz": "キロヘルツ",
    "km": "キロメートル",
    "kg": "キログラム",
    "cm": "センチメートル",
    "mm": "ミリメートル",
    "m": "メートル",
    "g": "グラム",
    "mg": "ミリグラム",
    "ml": "ミリリットル",
    "l": "リットル",
    "℃": "度",
    "°c": "度",
    "%": "パーセント",
    "円": "円",
    "¥": "円",
    "$": "ドル",
}

_SYMBOL_REPLACEMENTS = {
    "&": "アンド",
    "@": "アット",
    "#": "シャープ",
    "+": "プラス",
    "%": "パーセント",
    "=": "イコール",
}


def looks_japanese(text: str | None) -> bool:
    return bool(_JP_TEXT_PATTERN.search(str(text or "")))


def _append_operation(
    operations: list[dict[str, Any]],
    op_type: str,
    before: str,
    after: str,
    value: Any = None,
    force: bool = False,
) -> None:
    if before == after and not force:
        return
    operation: dict[str, Any] = {"type": op_type, "from": before, "to": after}
    if value is not None:
        operation["value"] = value
    operations.append(operation)


def normalize_text_for_sbv2_jp_extra(text: str | None, settings: dict | None) -> dict[str, Any]:
    settings = settings or {}
    original = str(text or "")
    operations: list[dict[str, Any]] = []
    warnings: list[str] = []

    current = original
    looks_before = looks_japanese(current)

    # 1) NFKC / control char cleanup
    before = current
    current = unicodedata.normalize("NFKC", current)
    current = _CONTROL_PATTERN.sub("", current)
    _append_operation(operations, "nfkc_control_cleanup", before, current)

    # 2) whitespace and newline cleanup
    before = current
    current = current.replace("\r\n", "\n").replace("\r", "\n")
    current = "\n".join(line.strip() for line in current.split("\n"))
    current = _MULTISPACE_PATTERN.sub(" ", current)
    current = re.sub(r"\n{3,}", "\n\n", current).strip()
    _append_operation(operations, "whitespace_newline_cleanup", before, current)

    # 3) URL/email policy
    before = current
    url_policy = str(
        settings.get("sbv2_jp_extra_url_policy")
        or settings.get("sbv2_jp_extra_url_email_policy")
        or settings.get("url_policy")
        or settings.get("url_email_policy")
        or "skip"
    ).strip().lower()
    if url_policy == "remove":
        url_policy = "skip"
    elif url_policy == "replace":
        url_policy = "readable"
    if url_policy not in {"skip", "readable"}:
        warnings.append(f"unknown url policy: {url_policy}. fallback=skip")
        url_policy = "skip"
    if url_policy == "skip":
        current = _EMAIL_PATTERN.sub(" ", _URL_PATTERN.sub(" ", current))
    else:
        current = _EMAIL_PATTERN.sub(" メールアドレス ", _URL_PATTERN.sub(" URL ", current))
    current = _MULTISPACE_PATTERN.sub(" ", current).strip()
    _append_operation(operations, "url_policy", before, current, url_policy)

    # 4) emoji policy
    before = current
    emoji_policy = str(
        settings.get("sbv2_jp_extra_emoji_policy")
        or settings.get("emoji_policy")
        or "skip"
    ).strip().lower()
    if emoji_policy == "remove":
        emoji_policy = "skip"
    elif emoji_policy == "replace":
        emoji_policy = "describe"
    if emoji_policy not in {"skip", "describe", "keep"}:
        warnings.append(f"unknown emoji policy: {emoji_policy}. fallback=skip")
        emoji_policy = "skip"
    if emoji_policy == "keep":
        pass
    elif emoji_policy == "describe":
        current = _EMOJI_PATTERN.sub(" 絵文字 ", current)
    else:
        current = _EMOJI_PATTERN.sub("", current)
    current = _MULTISPACE_PATTERN.sub(" ", current).strip()
    _append_operation(operations, "emoji_policy", before, current, emoji_policy)

    # 5) symbol policy
    before = current
    symbol_policy = str(
        settings.get("sbv2_jp_extra_symbol_policy")
        or settings.get("symbol_policy")
        or "readable"
    ).strip().lower()
    if symbol_policy == "remove":
        symbol_policy = "skip"
    elif symbol_policy == "replace":
        symbol_policy = "readable"
    if symbol_policy not in {"skip", "readable", "keep"}:
        warnings.append(f"unknown symbol policy: {symbol_policy}. fallback=readable")
        symbol_policy = "readable"
    if symbol_policy == "skip":
        current = re.sub(r"[^\w\sぁ-んァ-ン一-龯。、，．！？!?\-ー・]", " ", current)
    elif symbol_policy == "readable":
        for symbol, replacement in _SYMBOL_REPLACEMENTS.items():
            current = current.replace(symbol, f" {replacement} ")
    current = _MULTISPACE_PATTERN.sub(" ", current).strip()
    _append_operation(operations, "symbol_policy", before, current, symbol_policy)

    # 6) notation rules (No. / version)
    before = current
    current = _NO_PATTERN.sub(lambda m: f"ナンバー{m.group('number')}", current)
    current = _VERSION_PATTERN.sub(lambda m: f"バージョン{m.group('version')}", current)
    _append_operation(operations, "notation_rules", before, current, {"no": "ナンバー", "version": "バージョン"})

    # 7) number + unit readability
    before = current

    def _replace_unit(m: re.Match[str]) -> str:
        number = m.group("number")
        unit = m.group("unit")
        unit_readable = _UNIT_READABLE_MAP.get(unit.lower(), _UNIT_READABLE_MAP.get(unit, unit))
        return f"{number}{unit_readable}"

    def _replace_currency_prefix(m: re.Match[str]) -> str:
        currency = m.group("currency")
        number = m.group("number")
        currency_readable = _UNIT_READABLE_MAP.get(currency, currency)
        return f"{number}{currency_readable}"

    current = _CURRENCY_PREFIX_PATTERN.sub(_replace_currency_prefix, current)
    current = _NUMBER_UNIT_PATTERN.sub(_replace_unit, current)
    current = current.replace("$", " ドル ").replace("¥", " 円 ")
    current = _MULTISPACE_PATTERN.sub(" ", current).strip()
    _append_operation(operations, "number_unit_readability", before, current)

    # 8) english dictionary replacement + strategy
    before = current
    english_policy = str(
        settings.get("sbv2_jp_extra_english_to_katakana")
        or settings.get("sbv2_jp_extra_english_policy")
        or settings.get("english_to_katakana")
        or settings.get("english_policy")
        or "rule"
    ).strip().lower()
    english_dict_raw = (
        settings.get("sbv2_jp_extra_english_dict")
        or settings.get("english_dict")
        or {}
    )
    english_dict = {str(k).lower(): str(v) for k, v in english_dict_raw.items()} if isinstance(english_dict_raw, dict) else {}
    if not english_dict:
        english_dict = dict(_DEFAULT_ENGLISH_DICT)

    if english_policy == "rule":
        def _replace_en_word(m: re.Match[str]) -> str:
            token = m.group(0)
            return english_dict.get(token.lower(), token)

        current = _ASCII_WORD_PATTERN.sub(_replace_en_word, current)
    elif english_policy == "llm":
        segments = [m.group(0) for m in _ASCII_WORD_PATTERN.finditer(current)]
        llm_map = katakanaize_english_segments_with_llm(segments, english_dict=english_dict)
        current = _ASCII_WORD_PATTERN.sub(
            lambda m: llm_map.get(m.group(0), english_dict.get(m.group(0).lower(), m.group(0))),
            current,
        )
    elif english_policy == "skip":
        current = _ASCII_WORD_PATTERN.sub(" ", current)
    elif english_policy == "none":
        pass
    else:
        warnings.append(f"unknown english_to_katakana policy: {english_policy}. fallback=rule")
        current = _ASCII_WORD_PATTERN.sub(lambda m: english_dict.get(m.group(0).lower(), m.group(0)), current)
    current = _MULTISPACE_PATTERN.sub(" ", current).strip()
    _append_operation(operations, "english_to_katakana", before, current, english_policy, force=True)

    looks_after = looks_japanese(current)
    if current and not looks_after:
        warnings.append("normalized text still does not look Japanese.")

    return {
        "original_text": original,
        "normalized_text": current,
        "text": current,
        "operations": operations,
        "warnings": warnings,
        "looks_japanese_before": looks_before,
        "looks_japanese_after": looks_after,
        "changed": current != original,
    }
