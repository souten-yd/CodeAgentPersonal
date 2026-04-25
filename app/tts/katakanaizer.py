from __future__ import annotations

import json
import logging
import os
import re
from typing import Iterable

import requests

_logger = logging.getLogger("style_bert_vits2")

_JSON_BLOCK_PATTERN = re.compile(r"\{.*\}", re.DOTALL)
_KATAKANA_CACHE: dict[str, str] = {}
_DEFAULT_TIMEOUT_SEC = 4.0
_DEFAULT_ENDPOINT = "http://127.0.0.1:8000/v1/chat/completions"
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


def _endpoint() -> str:
    endpoint = str(os.environ.get("CODEAGENT_KATAKANA_LLM_ENDPOINT", _DEFAULT_ENDPOINT)).strip()
    if "/tts/translate-text" in endpoint.lower():
        raise ValueError("katakana llm endpoint must not be /tts/translate-text")
    return endpoint


def katakanaize_english_segments_with_llm(
    segments: Iterable[str],
    *,
    english_dict: dict[str, str] | None = None,
    timeout_sec: float | None = None,
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
        cached = _KATAKANA_CACHE.get(token)
        if cached:
            result[token] = cached
            continue
        dict_value = dictionary.get(token.lower())
        if dict_value:
            result[token] = dict_value
            _KATAKANA_CACHE[token] = dict_value
            continue
        pending.append(token)

    if not pending:
        return result

    timeout_value = float(timeout_sec or _DEFAULT_TIMEOUT_SEC)
    model = str(os.environ.get("CODEAGENT_KATAKANA_LLM_MODEL", _DEFAULT_MODEL)).strip() or _DEFAULT_MODEL
    endpoint = _endpoint()

    try:
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
            value = _normalize_segment(converted.get(token))
            if not value:
                value = dictionary.get(token.lower(), token)
            result[token] = value
            _KATAKANA_CACHE[token] = value
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
            _KATAKANA_CACHE[token] = fallback

    return result
