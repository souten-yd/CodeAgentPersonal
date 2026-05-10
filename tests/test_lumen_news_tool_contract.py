from pathlib import Path

from app.lumen.intent import detect_lumen_intent
from app.lumen.news import LumenNewsRequest, LumenNewsResult, build_nexus_news_handoff, compress_news_result_for_llm, run_lumen_news_tool
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


def test_lumen_news_metadata_shape_and_failed_context(monkeypatch):
    def fake_collect(topic, *, profile=None):
        return {
            "queries": ["AI news"],
            "items": [],
            "search": {
                "retrieved_at": "2026-05-10T00:00:00+00:00",
                "provider_status": [{"provider": "searxng", "ok": False, "item_count": 0, "error_count": 1, "skipped": False, "endpoint_configured": False}],
                "overall_status": "failed",
                "metadata": {"final_diversity": {}, "deduped_union_count": 0, "evidence_metadata": {"full_text_scraped": False}},
            },
        }

    monkeypatch.setattr("app.lumen.news.collect_news_research_sources", fake_collect)
    result = run_lumen_news_tool(LumenNewsRequest(message="AI最新ニュース"))
    assert result.ok is False
    assert result.metadata["overall_status"] == "failed"
    assert result.metadata["item_count"] == 0
    assert result.metadata["final_diversity"] == {}
    assert result.metadata["provider_status"][0]["endpoint_configured"] is False
    context = compress_news_result_for_llm(result)
    assert "推測でニュース本文や見出しを作らず" in context
    assert "item_count=0" in context


def test_lumen_news_result_metadata_defaults_for_display():
    result = LumenNewsResult(metadata={
        "overall_status": "failed",
        "provider_status": [],
        "final_diversity": {},
        "item_count": 0,
        "save_evidence": False,
        "deep_research_started": False,
        "source_profile": "news",
    })
    for key in ["overall_status", "provider_status", "final_diversity", "item_count", "save_evidence", "deep_research_started", "source_profile"]:
        assert key in result.metadata
