from unittest.mock import patch

from app.nexus.research_agent import ResearchAgentInput, _filter_stub_candidates, run_research_job
from app.nexus.research_api import get_research_job_answer
from app.nexus.source_collector import collect_source_candidates


def test_collect_source_candidates_preserves_stub_metadata():
    candidates = collect_source_candidates(
        search_items=[{"url": "https://example.com/stub", "title": "Stub", "is_stub": True}]
    )
    assert candidates[0]["metadata"]["is_stub"] is True


def test_stub_candidates_are_filtered_in_deep_mode():
    filtered, count = _filter_stub_candidates(
        [{"url": "https://example.com/stub", "metadata": {"is_stub": True}}],
        ResearchAgentInput(query="q", mode="deep"),
    )
    assert filtered == []
    assert count == 1


def test_stub_candidates_are_preserved_in_standard_mode():
    candidates = [{"url": "https://example.com/stub", "metadata": {"is_stub": True}}]
    filtered, count = _filter_stub_candidates(candidates, ResearchAgentInput(query="q"))
    assert filtered == candidates
    assert count == 0


def test_stub_only_deep_job_degrades_without_citing_stub():
    fake_search = {"items": [{"title": "stub", "url": "https://example.com/stub", "is_stub": True}]}
    candidates = collect_source_candidates(search_items=fake_search["items"])

    with patch("app.nexus.research_agent.plan_web_queries", return_value=["q"]), patch(
        "app.nexus.research_agent.run_web_search", return_value=fake_search
    ), patch("app.nexus.research_agent.collect_source_candidates", return_value=candidates), patch(
        "app.nexus.research_agent.rank_source_candidates", return_value=candidates
    ), patch("app.nexus.research_agent.update_job") as mocked_update, patch(
        "app.nexus.research_agent.append_job_event"
    ) as mocked_event:
        result = run_research_job(ResearchAgentInput(query="q", mode="deep"), job_id="job-stub")

    assert result["sources"] == []
    assert "根拠付き回答は生成できません" in result["answer"]["answer_markdown"]
    assert "[S1]" not in result["answer"]["answer_markdown"]
    assert any(call.kwargs.get("status") == "degraded" for call in mocked_update.call_args_list)
    assert any(call.args[1] == "stub_sources_filtered" for call in mocked_event.call_args_list if len(call.args) > 1)
    persisted_answer = get_research_job_answer("job-stub")["answer"]
    assert persisted_answer
    assert persisted_answer["output_incomplete"] is True
    assert persisted_answer["generation_mode"] == "stub_filtered_no_real_sources"
    assert persisted_answer["claim_analysis"]
