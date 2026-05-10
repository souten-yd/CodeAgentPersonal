from types import SimpleNamespace

from app.lumen.intent import LumenIntent
from app.services.lumen_runtime import should_enable_lumen_web_search


def _req(search_policy="auto"):
    return SimpleNamespace(search_policy=search_policy)


def test_weather_and_news_intents_disable_web_fallback():
    assert should_enable_lumen_web_search(LumenIntent(kind="weather"), _req()) is False
    assert should_enable_lumen_web_search(LumenIntent(kind="news"), _req()) is False


def test_web_intent_enables_web_search_unless_off():
    assert should_enable_lumen_web_search(LumenIntent(kind="web"), _req()) is True
    assert should_enable_lumen_web_search(LumenIntent(kind="web"), _req("off")) is False


def test_search_policy_on_still_does_not_override_weather_intent():
    assert should_enable_lumen_web_search(LumenIntent(kind="weather"), _req("on")) is False
