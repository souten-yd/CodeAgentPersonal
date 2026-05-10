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
_WEATHER_KEYWORDS = ("天気", "気温", "雨", "降水", "台風", "weather", "forecast")
_NEWS_KEYWORDS = ("ニュース", "最新情報", "速報", "今日の出来事", "headlines", "latest news", "cnbc", "yahooニュース")
_DEEP_RESEARCH_KEYWORDS = ("詳しく調査", "レポート", "根拠付き", "深掘り", "複数回検索", "長文調査")
_WEB_KEYWORDS = ("web", "ウェブ", "検索", "調べて", "サイト", "url", "http://", "https://")


def _contains_any(text: str, keywords: tuple[str, ...]) -> str | None:
    for keyword in keywords:
        if keyword in text:
            return keyword
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
