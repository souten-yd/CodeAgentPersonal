"""Lightweight Lumen intent detection.

This module only classifies messages so future PRs can decide whether to offer
weather/news/web assistance. It does not execute tools.
"""

from __future__ import annotations

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


def extract_weather_location_hint(message: str) -> str | None:
    """Extract a lightweight location hint from common Japanese weather asks.

    This intentionally avoids broad inference. The explicit request.location from
    the submit payload should be preferred by callers when present.
    """

    import re

    text = (message or "").strip()
    if not text:
        return None

    weather_terms = "天気|気温|雨|降水|傘|台風|暑い|寒い"
    cleanup_terms = (
        "今日|明日|明後日|週末|今週|来週|の|は|で|に|を|教えて|教えてください|"
        r"どう|ですか|かな|？|\?|weather|forecast|temperature|rain"
    )
    patterns = (
        rf"^\s*(?P<loc>[^\sのはでにを、。！？?]+?)の(?:今日|明日|明後日|週末|今週|来週)?(?:{weather_terms})",
        rf"^\s*(?P<loc>[^\s、。！？?]+?)\s+(?:今日|明日|明後日|週末|今週|来週)?(?:の)?(?:{weather_terms})",
        rf"^\s*(?P<loc>[^\sのはでにを、。！？?]+?)(?:は|で|に)(?:今日|明日|明後日|週末|今週|来週)?(?:{weather_terms})",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            loc = re.sub(cleanup_terms, "", match.group("loc"), flags=re.IGNORECASE).strip()
            return loc or None
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
