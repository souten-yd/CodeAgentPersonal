from app.lumen.intent import detect_lumen_intent
from app.lumen.tools import plan_lumen_tools


def test_greetings_are_pure_chat():
    assert detect_lumen_intent("こんちは").kind == "chat"
    assert detect_lumen_intent("こんにちは").kind == "chat"


def test_weather_news_and_deep_research_intents():
    assert detect_lumen_intent("東京の天気").kind == "weather"
    assert detect_lumen_intent("今日のニュース").kind == "news"
    assert detect_lumen_intent("CNBCのニュース").kind == "news"
    assert detect_lumen_intent("Yahooニュース").kind == "news"
    assert detect_lumen_intent("詳しく調査してレポート").kind == "nexus_deep_research_suggestion"


def test_pure_chat_tool_plan_is_empty():
    intent = detect_lumen_intent("こんにちは")
    plan = plan_lumen_tools(intent=intent, tool_policy="auto", search_policy="auto")
    assert plan.tools == []
    assert plan.metadata["intent"] == "chat"
    assert plan.metadata["executed"] is False


def test_deep_research_suggestion_does_not_plan_lumen_tool():
    intent = detect_lumen_intent("詳しく調査してレポート")
    plan = plan_lumen_tools(intent=intent, tool_policy="on", search_policy="on")
    assert plan.tools == []
    assert plan.metadata["handoff"] == "nexus_deep_research"
    assert plan.metadata["executed"] is False
