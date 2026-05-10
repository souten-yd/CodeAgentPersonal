"""Lightweight Lumen intent detection.

This module only classifies messages so future PRs can decide whether to offer
weather/news/web assistance. It does not execute tools.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

LumenIntentKind = Literal["chat", "weather", "news", "web", "nexus_deep_research_suggestion"]


class LumenIntent(BaseModel):
    """A small intent label plus non-execution metadata for Lumen."""

    kind: LumenIntentKind = "chat"
    confidence: float = 0.0
    reason: str = "default_chat"


_GREETING_CHATS = {"こんちは", "こんにちは"}
_WEATHER_KEYWORDS = ("天気", "気温", "雨", "降水", "傘", "台風", "暑い", "寒い", "weather", "forecast", "temperature", "rain")
_NEWS_KEYWORDS = ("ニュース", "最新情報", "速報", "今日の出来事", "headlines", "latest news", "cnbc", "yahooニュース")
_DEEP_RESEARCH_KEYWORDS = ("詳しく調査", "レポート", "根拠付き", "深掘り", "複数回検索", "長文調査")
_WEB_KEYWORDS = ("web", "ウェブ", "検索", "調べて", "サイト", "url", "http://", "https://")


def _contains_any(text: str, keywords: tuple[str, ...]) -> str | None:
    for keyword in keywords:
        if keyword in text:
            return keyword
    return None


_WEATHER_TEMPORAL_TERMS = "今日|明日|明後日|週末|今週|来週|今夜|今朝"
_WEATHER_TERMS_PATTERN = "天気予報|天気|気温|雨|降水|傘|台風|暑い|寒い|weather|forecast|temperature|rain"
_WEATHER_TIME_HINTS = (
    ("day_after_tomorrow", ("明後日",)),
    ("tomorrow", ("明日",)),
    ("today", ("今日", "今夜", "今朝")),
    ("weekend", ("週末",)),
    ("this_week", ("今週",)),
    ("next_week", ("来週",)),
)


def _clean_weather_location_hint(location: str) -> str | None:
    loc = (location or "").strip()
    if not loc:
        return None
    loc = re.sub(rf"^(?:{_WEATHER_TEMPORAL_TERMS})の", "", loc)
    loc = re.sub(rf"(?:の)?(?:{_WEATHER_TERMS_PATTERN}).*", "", loc, flags=re.IGNORECASE)
    loc = re.sub(r"(?:を)?(?:教えてください|教えて|知りたい|お願いします).*", "", loc)
    loc = re.sub(r"[、。！？?\s]+$", "", loc).strip()
    if re.fullmatch(rf"(?:{_WEATHER_TEMPORAL_TERMS})", loc):
        return None
    return loc or None


def extract_weather_time_hint(message: str) -> str | None:
    """Extract a conservative temporal hint from common Japanese weather asks."""

    text = (message or "").strip()
    if not text:
        return None
    for hint, terms in _WEATHER_TIME_HINTS:
        if any(term in text for term in terms):
            return hint
    return None


def extract_weather_location_hint(message: str) -> str | None:
    """Extract a lightweight location hint from common Japanese weather asks.

    This intentionally avoids broad inference. The explicit request.location from
    the submit payload should be preferred by callers when present.
    """

    text = (message or "").strip()
    if not text:
        return None

    temporal_terms = _WEATHER_TEMPORAL_TERMS
    weather_terms = _WEATHER_TERMS_PATTERN
    patterns = (
        # 明日の横浜の天気 / 今日の横浜の天気予報
        rf"^\s*(?:{temporal_terms})の(?P<loc>[^\sのはでにを、。！？?]+?)の(?:{weather_terms})",
        # 横浜の明日の天気
        rf"^\s*(?P<loc>[^\sのはでにを、。！？?]+?)の(?:{temporal_terms})の(?:{weather_terms})",
        # 横浜で明日雨降る？ / 横浜は今日寒い？
        rf"^\s*(?P<loc>[^\sのはでにを、。！？?]+?)(?:は|で|に)(?:{temporal_terms})?(?:.*?)(?:{weather_terms})",
        # 既存: 横浜の天気
        rf"^\s*(?P<loc>[^\sのはでにを、。！？?]+?)の(?:{weather_terms})",
        # Existing whitespace-separated style: Yokohama weather / 横浜 今日 天気
        rf"^\s*(?P<loc>[^\s、。！？?]+?)\s+(?:{temporal_terms})?(?:の)?(?:{weather_terms})",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return _clean_weather_location_hint(match.group("loc"))
    return None


def detect_lumen_intent(message: str) -> LumenIntent:
    """Detect a lightweight Lumen intent without triggering tool execution."""

    raw = message or ""
    stripped = raw.strip()
    lowered = stripped.lower()
    if stripped in _GREETING_CHATS:
        return LumenIntent(kind="chat", confidence=1.0, reason="greeting_chat")

    matched = _contains_any(lowered, _DEEP_RESEARCH_KEYWORDS)
    if matched:
        return LumenIntent(kind="nexus_deep_research_suggestion", confidence=0.8, reason=f"deep_research_keyword:{matched}")

    matched = _contains_any(lowered, _WEATHER_KEYWORDS)
    if matched:
        return LumenIntent(kind="weather", confidence=0.8, reason=f"weather_keyword:{matched}")

    matched = _contains_any(lowered, _NEWS_KEYWORDS)
    if matched:
        return LumenIntent(kind="news", confidence=0.8, reason=f"news_keyword:{matched}")

    matched = _contains_any(lowered, _WEB_KEYWORDS)
    if matched:
        return LumenIntent(kind="web", confidence=0.6, reason=f"web_keyword:{matched}")

    return LumenIntent(kind="chat", confidence=0.3, reason="default_chat")
