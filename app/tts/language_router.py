from __future__ import annotations

import re
from typing import Any


def _norm_lang(value: Any, *, allow_same_as_asr: bool = False) -> str:
    raw = str(value or "").strip().lower()
    mapping = {
        "ja": "ja",
        "jp": "ja",
        "jpn": "ja",
        "japanese": "ja",
        "日本語": "ja",
        "en": "en",
        "eng": "en",
        "english": "en",
        "auto": "auto",
    }
    if allow_same_as_asr and raw in {"same_as_asr", "same as asr", "same-as-asr", "same"}:
        return "same_as_asr"
    return mapping.get(raw, "auto")


def _looks_japanese_light(text: str) -> bool:
    if not text:
        return False
    return bool(re.search(r"[\u3040-\u30ff\u3400-\u9fff]", text))


def _detect_text_language(text: str) -> str:
    t = str(text or "").strip()
    if not t:
        return "auto"
    if _looks_japanese_light(t):
        return "ja"
    if re.search(r"[A-Za-z]", t):
        return "en"
    return "auto"


def resolve_tts_language_route(req: dict, model_version: str | None) -> dict:
    settings = req.get("settings") or {}
    model_kind = "jp_extra" if "jp-extra" in str(model_version or "").lower() else "global"

    asr_language = _norm_lang(req.get("echo_asr_language") or settings.get("echo_asr_language") or req.get("asr_language"))
    output_language = _norm_lang(
        req.get("echo_output_language") or settings.get("echo_output_language") or req.get("output_language"),
        allow_same_as_asr=True,
    )
    tts_language = _norm_lang(req.get("echo_tts_language") or settings.get("echo_tts_language") or req.get("tts_language"))

    raw_text = str(req.get("raw_text") or req.get("text") or "")

    source_language = output_language
    if output_language == "same_as_asr":
        source_language = asr_language
    if source_language == "auto":
        source_language = _detect_text_language(raw_text)

    resolved_tts = "ja" if model_kind == "jp_extra" else (source_language if tts_language == "auto" else tts_language)
    if resolved_tts == "auto":
        resolved_tts = _detect_text_language(raw_text)

    needs_translation = False
    target = None
    if model_kind == "jp_extra":
        needs_translation = source_language not in {"ja", "auto"}
        target = "ja" if needs_translation else None
        resolved_tts = "ja"
    else:
        needs_translation = source_language in {"ja", "en"} and source_language != resolved_tts
        target = resolved_tts if needs_translation else None

    return {
        "model_kind": model_kind,
        "source_language": source_language,
        "output_language": output_language,
        "tts_language": resolved_tts if resolved_tts in {"ja", "en"} else "ja",
        "needs_translation": bool(needs_translation),
        "translation_target_language": target,
        "normalizer": "sbv2_jp_extra" if model_kind == "jp_extra" else "sbv2_global",
    }
