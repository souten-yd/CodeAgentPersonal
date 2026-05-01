from __future__ import annotations

import re
import unicodedata
from typing import Any

from .katakanaizer import (
    japanese_full_text_reading_with_llm,
    katakanaize_english_segments_with_llm,
)

_JP_TEXT_PATTERN = re.compile(r"[ぁ-ゟ゠-ヿ㐀-䶿一-鿿々〆〤ｦ-ﾟ]")
_URL_PATTERN = re.compile(
    r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+|www\.[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+",
    re.IGNORECASE,
)
_EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_EMOJI_TOKEN_PATTERN = re.compile(
    "(?:"
    "(?:[0-9#*]\uFE0F?\u20E3)"
    "|(?:[\U0001F1E6-\U0001F1FF]{2})"
    "|(?:"
    "[\u2600-\u26FF\u2700-\u27BF\U0001F300-\U0001FAFF]"
    "(?:\uFE0F)?"
    "(?:[\U0001F3FB-\U0001F3FF])?"
    "(?:\u200D[\u2600-\u26FF\u2700-\u27BF\U0001F300-\U0001FAFF](?:\uFE0F)?(?:[\U0001F3FB-\U0001F3FF])?)*"
    ")"
    ")"
)
_ASCII_WORD_PATTERN = re.compile(r"\b[A-Za-z][A-Za-z0-9_\-]*\b")
_EN_SEGMENT_PATTERN = re.compile(r"(?<![A-Za-z0-9])[A-Za-z][A-Za-z0-9]*(?:[-_][A-Za-z0-9]+)*(?![A-Za-z0-9])")
_CONTROL_PATTERN = re.compile(r"[\x00-\x08\x0B-\x1F\x7F]")
_MULTISPACE_PATTERN = re.compile(r"[ \t\u3000]+")
_JP_PUNCT_ASCII_MAP = str.maketrans({",": "、", "!": "！", "?": "？"})
_MARKDOWN_CODE_FENCE_PATTERN = re.compile(r"```+")
_MARKDOWN_HEADING_PATTERN = re.compile(r"(?m)^\s*#{1,6}\s*")
_MARKDOWN_BULLET_PATTERN = re.compile(r"(?m)^\s*[-*]\s+")
_SPACE_BEFORE_PUNCT_PATTERN = re.compile(r"\s+([、。！？：；，．・ー」』）)\]])")
_SPACE_AFTER_OPENING_PUNCT_PATTERN = re.compile(r"([「『（(])\s+")
_ASCII_ALPHA_PATTERN = re.compile(r"[A-Za-z]")
_NUMBER_UNIT_PATTERN = re.compile(
    r"(?P<number>\d+(?:[.,]\d+)?)\s*(?P<unit>vram|ghz|mhz|khz|tb|gb|mb|kb|kv|ma|kw|mw|km|kg|cm|mm|mg|ml|°C|v|a|w|m|g|l|℃|%|円|¥|\$)(?=$|[^A-Za-z])",
    re.IGNORECASE,
)
_CURRENCY_PREFIX_PATTERN = re.compile(r"(?P<currency>[$¥])\s*(?P<number>\d+(?:[.,]\d+)?)")
_NO_PATTERN = re.compile(r"(?<![A-Za-z0-9])No\.\s*(?P<number>\d+)(?![A-Za-z0-9])", re.IGNORECASE)
_VERSION_PATTERN = re.compile(r"(?<![A-Za-z0-9])v(?P<version>\d+(?:\.\d+)+)(?![A-Za-z0-9])", re.IGNORECASE)

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
    "python": "パイソン",
    "fastapi": "ファストエーピーアイ",
    "runpod": "ランポッド",
    "pc": "ピーシー",
    "kasanecore": "カサネコア",
    "style-bert-vits2": "スタイルバートブイツーツー",
    "jp-extra": "ジェーピーエクストラ",
    "vram": "ブイラム",
    "ok": "オーケー",
    "ng": "エヌジー",
    "ui": "ユーアイ",
    "webui": "ウェブユーアイ",
    "echo": "エコー",
    "vault": "ボルト",
    "echovault": "エコーボルト",
    "vad": "ブイエーディー",
    "directml": "ダイレクトエムエル",
    "rocm": "ロックエム",
    "vulkan": "バルカン",
    "whisper": "ウィスパー",
    "playwright": "プレイライト",
    "codeagent": "コードエージェント",
    "kasane": "カサネ",
    "nexus": "ネクサス",
    "upload": "アップロード",
    "stylebertvits2": "スタイルバートブイツーツー",
    "sbv2": "エスビーブイツー",
    "bert": "バート",
    "vits": "ビッツ",
    "onnx": "オニキス",
    "windows": "ウィンドウズ",
    "openrouter": "オープンルーター",
    "whispercpp": "ウィスパーシーピーピー",
    "whisper-cpp": "ウィスパーシーピーピー",
    "llama": "ラマ",
    "llamacpp": "ラマシーピーピー",
    "llama-cpp": "ラマシーピーピー",
    "gguf": "ジージーユーエフ",
    "mcp": "エムシーピー",
    "rag": "ラグ",
    "cuda": "クーダ",
    "pytorch": "パイトーチ",
    "transformers": "トランスフォーマーズ",
    "huggingface": "ハギングフェイス",
    "hf": "エイチエフ",
    "lmstudio": "エルエムスタジオ",
    "openwebui": "オープンウェブユーアイ",
    "searxng": "サークスエヌジー",
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
    "v": "ボルト",
    "kv": "キロボルト",
    "a": "アンペア",
    "ma": "ミリアンペア",
    "w": "ワット",
    "kw": "キロワット",
    "mw": "メガワット",
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


_ALPHA_SPELLING_KATAKANA = {
    "a": "エー",
    "b": "ビー",
    "c": "シー",
    "d": "ディー",
    "e": "イー",
    "f": "エフ",
    "g": "ジー",
    "h": "エイチ",
    "i": "アイ",
    "j": "ジェー",
    "k": "ケー",
    "l": "エル",
    "m": "エム",
    "n": "エヌ",
    "o": "オー",
    "p": "ピー",
    "q": "キュー",
    "r": "アール",
    "s": "エス",
    "t": "ティー",
    "u": "ユー",
    "v": "ブイ",
    "w": "ダブリュー",
    "x": "エックス",
    "y": "ワイ",
    "z": "ゼット",
}

_SYMBOL_REPLACEMENTS = {
    "&": "アンド",
    "@": "アット",
    "#": "シャープ",
    "+": "プラス",
    "%": "パーセント",
    "=": "イコール",
}


def _normalize_punctuation_for_jp_extra(text: str) -> str:
    current = text.translate(_JP_PUNCT_ASCII_MAP)
    # keep dot in decimals/version/No. while converting sentence punctuation
    current = re.sub(r"(?<![0-9A-Za-z])\.(?![0-9A-Za-z])", "。", current)
    current = re.sub(r"(?<![0-9A-Za-z])\.(?=\s|$)", "。", current)
    current = re.sub(r"(?<=\s)\.(?![0-9A-Za-z])", "。", current)
    # collapse repeated punctuation to natural pauses
    current = re.sub(r"。{2,}", "。", current)
    current = re.sub(r"、{2,}", "、", current)
    current = re.sub(r"！{2,}", "！", current)
    current = re.sub(r"？{2,}", "？", current)
    current = re.sub(r"(?:。\s*){2,}", "。", current)
    # convert ellipsis variants to period pause
    current = re.sub(r"(?:\.{2,}|…{1,})", "。", current)
    return current

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


def _fallback_spelling_reading(token: str) -> str:
    converted = token.replace("-", "・").replace("_", "・")
    mapped: list[str] = []
    for ch in converted:
        lower = ch.lower()
        if "a" <= lower <= "z":
            mapped.append(_ALPHA_SPELLING_KATAKANA[lower])
        elif ch.isdigit():
            mapped.append(ch)
        elif ch == "・":
            mapped.append("・")
    result = "".join(mapped)
    result = re.sub(r"・{2,}", "・", result).strip("・ ")
    return result


def normalize_text_for_japanese_tts(text: str | None, settings: dict | None) -> dict[str, Any]:
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

    # 2.5) markdown cleanup (preserve readable structure)
    before = current
    current = _MARKDOWN_CODE_FENCE_PATTERN.sub("", current)
    current = _MARKDOWN_HEADING_PATTERN.sub("", current)
    current = _MARKDOWN_BULLET_PATTERN.sub("・", current)
    _append_operation(operations, "markdown_cleanup", before, current)

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
        current = _EMAIL_PATTERN.sub(" 。 ", _URL_PATTERN.sub(" 。 ", current))
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
        emoji_policy = "skip"
    elif emoji_policy == "describe":
        emoji_policy = "skip"
    if emoji_policy not in {"skip", "describe", "keep"}:
        warnings.append(f"unknown emoji policy: {emoji_policy}. fallback=skip")
        emoji_policy = "skip"
    if emoji_policy == "keep":
        pass
    else:
        def _remove_emoji(m: re.Match[str]) -> str:
            token = m.group(0)
            _append_operation(operations, "emoji_removed", token, "", "emoji_policy_skip")
            return " "

        current = _EMOJI_TOKEN_PATTERN.sub(_remove_emoji, current)
    current = _MULTISPACE_PATTERN.sub(" ", current).strip()
    _append_operation(operations, "emoji_policy", before, current, emoji_policy)

    # 4.5) symbol policy
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
        current = re.sub(r"[^\w\sぁ-んァ-ン一-龯々〆〤。、，．！？：；「」『』（）()!?\-ー・]", " ", current)
    elif symbol_policy == "readable":
        for symbol, replacement in _SYMBOL_REPLACEMENTS.items():
            current = current.replace(symbol, f" {replacement} ")
    current = _MULTISPACE_PATTERN.sub(" ", current)
    current = _SPACE_BEFORE_PUNCT_PATTERN.sub(r"\1", current)
    current = _SPACE_AFTER_OPENING_PUNCT_PATTERN.sub(r"\1", current)
    current = current.strip()
    _append_operation(operations, "symbol_policy", before, current, symbol_policy)

    # 5) notation rules (No. / version)
    before = current
    current = _NO_PATTERN.sub(lambda m: f"ナンバー{m.group('number')}", current)
    current = _VERSION_PATTERN.sub(lambda m: f"バージョン{m.group('version')}", current)
    _append_operation(operations, "notation_rules", before, current, {"no": "ナンバー", "version": "バージョン"})

    # 6) number + unit readability
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
    current = _MULTISPACE_PATTERN.sub(" ", current)
    current = _SPACE_BEFORE_PUNCT_PATTERN.sub(r"\1", current)
    current = current.strip()
    _append_operation(operations, "number_unit_readability", before, current)

    # 6.5) JP-Extra punctuation normalization/retention
    before = current
    current = _normalize_punctuation_for_jp_extra(current)
    _append_operation(operations, "jp_punctuation_normalization", before, current)

    # 7) english dictionary replacement + strategy
    before = current
    english_policy = str(
        settings.get("sbv2_jp_extra_english_to_katakana")
        or settings.get("sbv2_jp_extra_english_policy")
        or settings.get("english_to_katakana")
        or settings.get("english_policy")
        or "llm"
    ).strip().lower()
    english_dict_raw = (
        settings.get("sbv2_jp_extra_english_dict")
        or settings.get("english_dict")
        or {}
    )
    english_dict = dict(_DEFAULT_ENGLISH_DICT)
    if isinstance(english_dict_raw, dict):
        english_dict.update({str(k).lower(): str(v) for k, v in english_dict_raw.items()})

    def _dict_replace(text: str) -> str:
        return _EN_SEGMENT_PATTERN.sub(lambda m: english_dict.get(m.group(0).lower(), m.group(0)), text)

    if english_policy == "skip":
        current = _EN_SEGMENT_PATTERN.sub(" ", current)
    elif english_policy == "none":
        pass
    elif english_policy in {"rule", "llm"}:
        current = _dict_replace(current)
        unresolved_segments = [
            m.group(0)
            for m in _EN_SEGMENT_PATTERN.finditer(current)
            if not english_dict.get(m.group(0).lower())
        ]
        if english_policy == "llm" and unresolved_segments:
            try:
                llm_result = katakanaize_english_segments_with_llm(
                    unresolved_segments,
                    context=current,
                    english_dict=english_dict,
                    raise_on_failure=True,
                    return_summary=True,
                )
                llm_map = dict((llm_result or {}).get("result") or {})
                llm_summary = dict((llm_result or {}).get("summary") or {})
                operations.append(
                    {
                        "type": "english_llm_katakanaize",
                        "value": {
                            "accepted": dict(llm_summary.get("accepted") or {}),
                            "rejected": dict(llm_summary.get("rejected") or {}),
                        },
                    }
                )
                current = _EN_SEGMENT_PATTERN.sub(
                    lambda m: llm_map.get(m.group(0), english_dict.get(m.group(0).lower(), m.group(0))),
                    current,
                )
            except Exception as exc:
                warnings.append(f"english llm katakanaize failed: {exc}")
                operations.append({
                    "type": "warning",
                    "category": "english_katakanaize",
                    "level": "warning",
                    "message": f"english llm katakanaize failed: {exc}",
                    "value": {"policy": english_policy, "fallback": "dictionary_only"},
                })
    else:
        warnings.append(f"unknown english_to_katakana policy: {english_policy}. fallback=llm")
        current = _dict_replace(current)
    current = _MULTISPACE_PATTERN.sub(" ", current)
    current = _SPACE_BEFORE_PUNCT_PATTERN.sub(r"\1", current)
    current = _SPACE_AFTER_OPENING_PUNCT_PATTERN.sub(r"\1", current)
    current = current.strip()
    _append_operation(operations, "english_to_katakana", before, current, english_policy, force=True)

    # 7.5) full-text Japanese reading normalization
    before = current
    full_text_enabled = bool(settings.get("sbv2_jp_extra_full_text_reading_normalization", False))
    full_text_mode = str(settings.get("sbv2_jp_extra_full_text_reading_mode", "llm")).strip().lower()
    full_text_dict_raw = settings.get("sbv2_jp_extra_japanese_reading_dict") or {}
    full_text_dict = (
        {str(k): str(v) for k, v in full_text_dict_raw.items()}
        if isinstance(full_text_dict_raw, dict)
        else {}
    )
    dict_applied_keys: list[str] = []
    if full_text_dict:
        for key, value in sorted(full_text_dict.items(), key=lambda item: len(item[0]), reverse=True):
            if key and key in current:
                current = current.replace(key, value)
                dict_applied_keys.append(key)
    llm_applied = False
    llm_warning: str | None = None
    if full_text_enabled and full_text_mode == "llm":
        try:
            llm_text = japanese_full_text_reading_with_llm(current)
            if llm_text:
                current = llm_text
                llm_applied = True
        except Exception as exc:
            llm_warning = f"japanese full text llm reading failed: {exc}"
            warnings.append(llm_warning)
    elif full_text_enabled and full_text_mode not in {"dict", "llm"}:
        warnings.append(f"unknown full text reading mode: {full_text_mode}. fallback=dict")
    operations.append(
        {
            "type": "japanese_full_text_reading",
            "before": before,
            "after": current,
            "value": {
                "japanese_reading_dict": dict_applied_keys,
                "japanese_full_text_llm_reading": full_text_mode == "llm",
                "accepted": {"dict": bool(dict_applied_keys), "llm": llm_applied},
                "warnings": [llm_warning] if llm_warning else [],
            },
        }
    )

    before = current
    remaining_before = [m.group(0) for m in _EN_SEGMENT_PATTERN.finditer(current)]
    if remaining_before:
        for token in sorted(set(remaining_before), key=len, reverse=True):
            spelling = _fallback_spelling_reading(token) or "英語"
            current = re.sub(rf"(?<![A-Za-z0-9]){re.escape(token)}(?![A-Za-z0-9])", spelling, current)
        remaining_after = [m.group(0) for m in _EN_SEGMENT_PATTERN.finditer(current)]
        if remaining_after:
            current = _EN_SEGMENT_PATTERN.sub("英語", current)
            remaining_after = [m.group(0) for m in _EN_SEGMENT_PATTERN.finditer(current)]
        warnings.append("english_spelling_fallback_applied")
        if remaining_after:
            warnings.append("english_remains_after_katakanaize")
        operations.append({"type": "english_fallback", "from": before, "to": current, "value": {"mode": "spelling_or_replace", "remaining_before": remaining_before, "remaining_after": remaining_after}})
    else:
        remaining_after = []

    if _ASCII_ALPHA_PATTERN.search(current):
        if english_policy != "skip":
            rerun = _EN_SEGMENT_PATTERN.sub(lambda m: english_dict.get(m.group(0).lower(), m.group(0)), current)
            if rerun != current:
                current = rerun
        if _ASCII_ALPHA_PATTERN.search(current):
            warnings.append("ascii_alpha_remains_in_final_text")
            operations.append(
                {
                    "type": "warning",
                    "category": "final_ascii_check",
                    "level": "warning",
                    "message": "ASCII alphabets remain in final text after normalization",
                }
            )

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
        "english_remaining": remaining_after,
        "changed": current != original,
    }


def normalize_text_for_sbv2_jp_extra(text: str | None, settings: dict | None) -> dict[str, Any]:
    return normalize_text_for_japanese_tts(text, settings)


def preprocess_text_for_tts(
    text: str,
    *,
    target_language: str,
    model_kind: str = "style_bert_vits2",
    is_jp_extra: bool = False,
    settings: dict | None = None,
) -> dict[str, Any]:
    original = str(text or "")
    lang = str(target_language or "").strip().lower()
    normalized_target = "ja" if lang in {"ja", "jp", "japanese", "日本語"} else "en"
    operations: list[dict[str, Any]] = []
    warnings: list[str] = []
    if normalized_target == "ja":
        jp = normalize_text_for_japanese_tts(original, settings or {})
        return {
            "text": str(jp.get("text") or ""),
            "original_text": original,
            "target_language": "ja",
            "operations": list(jp.get("operations") or []),
            "warnings": list(jp.get("warnings") or []),
            "english_remaining": list(jp.get("english_remaining") or []),
            "changed": bool(jp.get("changed")),
            "model_kind": model_kind,
            "is_jp_extra": is_jp_extra,
        }

    return {
        "text": original,
        "original_text": original,
        "target_language": "en",
        "operations": operations,
        "warnings": warnings,
        "english_remaining": [],
        "changed": False,
        "model_kind": model_kind,
        "is_jp_extra": is_jp_extra,
    }
