from __future__ import annotations

import json
import logging
import os
import re
from typing import Iterable

from .katakana_cache import KatakanaPersistentCache

import requests

_logger = logging.getLogger("style_bert_vits2")

_JSON_BLOCK_PATTERN = re.compile(r"\{.*\}", re.DOTALL)
_KATAKANA_CACHE: dict[str, str] = {}
_PERSISTENT_CACHE = KatakanaPersistentCache()
_DEFAULT_TIMEOUT_SEC = 4.0
_DEFAULT_ENDPOINT = "http://127.0.0.1:8080/v1/chat/completions"
_DEFAULT_MODEL = "local-llm"


def _normalize_segment(segment: str | None) -> str:
    return str(segment or "").strip()


def _extract_json_object(content: str) -> dict[str, str]:
    text = str(content or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        return {str(k): str(v) for k, v in parsed.items()} if isinstance(parsed, dict) else {}
    except Exception:
        pass
    match = _JSON_BLOCK_PATTERN.search(text)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0))
        return {str(k): str(v) for k, v in parsed.items()} if isinstance(parsed, dict) else {}
    except Exception:
        return {}



_URL_PATTERN = re.compile(r"https?://|www\.", re.IGNORECASE)
_KATAKANA_ALLOWED_PATTERN = re.compile(r"^[ァ-ヶーぁ-ゖー・0-9０-９]+$")
_DESCRIPTION_MARKERS = (
    "読みは",
    "読みです",
    "と読みます",
    "です",
)


def _is_valid_katakana_reading(token: str, value: str) -> bool:
    text = _normalize_segment(value)
    if not text:
        return False
    if len(text) > 64:
        return False
    if _URL_PATTERN.search(text):
        return False
    if re.search(r"[A-Za-z]", text):
        return False
    lower = text.lower()
    if any(marker in lower for marker in ("{", "}", "\"", "description", "explanation", "segments")):
        return False
    if any(marker in text for marker in _DESCRIPTION_MARKERS):
        return False
    if not _KATAKANA_ALLOWED_PATTERN.fullmatch(text):
        return False
    if len(text) > max(24, len(token) * 4):
        return False
    return True


def _endpoint() -> str:
    explicit = str(os.environ.get("CODEAGENT_KATAKANA_LLM_ENDPOINT", "")).strip()
    if explicit:
        endpoint = explicit
    else:
        codeagent_base = str(os.environ.get("CODEAGENT_LLM_BASE_URL", "")).strip().rstrip("/")
        if codeagent_base:
            endpoint = f"{codeagent_base}/v1/chat/completions"
        else:
            openai_base = str(os.environ.get("OPENAI_BASE_URL", "")).strip().rstrip("/")
            if openai_base:
                endpoint = (
                    f"{openai_base}/chat/completions"
                    if openai_base.endswith("/v1")
                    else f"{openai_base}/v1/chat/completions"
                )
            else:
                endpoint = _DEFAULT_ENDPOINT
    if "/tts/translate-text" in endpoint.lower():
        raise ValueError("katakana llm endpoint must not be /tts/translate-text")
    return endpoint


def katakanaize_english_segments_with_llm(
    segments: Iterable[str],
    *,
    english_dict: dict[str, str] | None = None,
    timeout_sec: float | None = None,
    raise_on_failure: bool = False,
) -> dict[str, str]:
    normalized_segments: list[str] = []
    seen: set[str] = set()
    for segment in segments:
        token = _normalize_segment(segment)
        if not token or token in seen:
            continue
        seen.add(token)
        normalized_segments.append(token)

    if not normalized_segments:
        return {}

    dictionary = {str(k).lower(): str(v) for k, v in (english_dict or {}).items()}
    result: dict[str, str] = {}
    pending: list[str] = []

    for token in normalized_segments:
        dict_value = dictionary.get(token.lower())
        if dict_value:
            result[token] = dict_value
            _KATAKANA_CACHE[token] = dict_value
            continue
        persistent_value = _PERSISTENT_CACHE.get(token)
        if persistent_value:
            _logger.info("[SBV2][normalize][persistent_cache_hit] token=%s", token)
            result[token] = persistent_value
            _KATAKANA_CACHE[token] = persistent_value
            continue
        cached = _KATAKANA_CACHE.get(token)
        if cached:
            _logger.info("[SBV2][normalize][memory_cache_hit] token=%s", token)
            result[token] = cached
            continue
        pending.append(token)

    if not pending:
        return result

    timeout_value = float(timeout_sec or _DEFAULT_TIMEOUT_SEC)
    model = str(os.environ.get("CODEAGENT_KATAKANA_LLM_MODEL", _DEFAULT_MODEL)).strip() or _DEFAULT_MODEL
    endpoint = _endpoint()

    try:
        _logger.info("[SBV2][normalize][llm_request_count] count=%d", len(pending))
        _logger.info("[SBV2][normalize][katakana_llm_start] pending=%d", len(pending))
        response = requests.post(
            endpoint,
            timeout=timeout_value,
            headers={"Content-Type": "application/json"},
            json={
                "model": model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Convert English terms to natural Japanese Katakana readings. "
                            "Return ONLY one JSON object. Keys must exactly match the input strings."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps({"segments": pending}, ensure_ascii=False),
                    },
                ],
            },
        )
        response.raise_for_status()
        body = response.json() if response.content else {}
        content = (
            (
                ((body.get("choices") or [{}])[0].get("message") or {}).get("content")
                if isinstance(body, dict)
                else ""
            )
            or ""
        )
        converted = _extract_json_object(content)
        if not converted:
            raise ValueError("llm returned empty/non-json mapping")
        converted_count = 0
        for token in pending:
            raw_value = _normalize_segment(converted.get(token))
            if _is_valid_katakana_reading(token, raw_value):
                value = raw_value
                _KATAKANA_CACHE[token] = value
                _PERSISTENT_CACHE.set(token, value, created_by="llm")
                _logger.info("[SBV2][normalize][persistent_cache_saved] token=%s", token)
            else:
                value = dictionary.get(token.lower(), token)
                if value != token:
                    _KATAKANA_CACHE[token] = value
            result[token] = value
            if value != token:
                converted_count += 1
        _logger.info(
            "[SBV2][normalize][katakana_llm_done] pending=%d converted=%d cache_size=%d",
            len(pending),
            converted_count,
            len(_KATAKANA_CACHE),
        )
    except Exception as exc:
        _logger.warning(
            "[SBV2][normalize][katakana_llm_fallback] pending=%d reason=%s",
            len(pending),
            exc,
        )
        for token in pending:
            fallback = dictionary.get(token.lower(), token)
            result[token] = fallback
            if fallback != token:
                _KATAKANA_CACHE[token] = fallback
        if raise_on_failure:
            raise RuntimeError(f"katakana llm failed: {exc}") from exc

    return result
