from pathlib import Path

from app.lumen.intent import detect_lumen_intent
from app.lumen.news import build_nexus_news_handoff, compress_news_result_for_llm, run_lumen_news_tool
from app.lumen.tools import execute_lumen_tool_plan, plan_lumen_tools
from app.lumen.budgets import LumenNewsBudget


def test_lumen_news_module_contract_exists():
    assert Path("app/lumen/news.py").exists()
    assert run_lumen_news_tool
    assert compress_news_result_for_llm


def test_news_intents_detected():
    assert detect_lumen_intent("最新ニュースを教えて").kind == "news"
    assert detect_lumen_intent("CNBCのニュース").kind == "news"
    assert detect_lumen_intent("Yahooニュース").kind == "news"


def test_deep_research_handoff_for_report_request():
    intent = detect_lumen_intent("AIニュースを詳しく調査してレポート")
    assert intent.kind == "nexus_deep_research_suggestion"
    handoff = build_nexus_news_handoff("AIニュースを詳しく調査してレポート")
    assert handoff["auto_started"] is False
    assert handoff["payload"]["source_profile"] == "news"


def test_lumen_news_plan_is_executable_but_does_not_save_or_autostart(monkeypatch):
    intent = detect_lumen_intent("最新ニュース")
    plan = plan_lumen_tools(intent=intent, news_budget=LumenNewsBudget(max_total_items=3))
    assert plan.tools == ["news"]
    assert plan.metadata["executable"] is True

    class FakeResult:
        ok = True
        def model_dump(self):
            return {"ok": True, "metadata": {"save_evidence": False, "deep_research_started": False}, "sources": []}
    monkeypatch.setattr("app.lumen.tools.run_lumen_news_tool", lambda request: FakeResult())
    monkeypatch.setattr("app.lumen.tools.compress_news_result_for_llm", lambda result: "digest")
    results = execute_lumen_tool_plan(plan=plan, intent=intent, message="最新ニュース")
    assert results[0].tool == "news"
    assert results[0].metadata["metadata"]["save_evidence"] is False
    assert results[0].metadata["metadata"]["deep_research_started"] is False


def test_yahoo_handoff_personal_use_metadata():
    # Config-level guarantee used by Lumen digest when Yahoo RSS is included.
    import json
    data = json.loads(Path("config/lumen/rss_feeds.json").read_text(encoding="utf-8"))
    yahoo = next(feed for feed in data["feeds"] if "Yahoo" in feed["name"])
    assert yahoo["personal_use_only"] is True
