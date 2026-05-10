from app.nexus.news import run_news_mvp
from app.nexus.news_sources import (
    NewsResearchSourceProfile,
    collect_news_research_sources,
    convert_news_items_to_evidence,
)
from app.nexus.research_agent import ResearchAgentInput


def test_news_research_source_profile_contract():
    profile = NewsResearchSourceProfile(source_profile="news", save_evidence=True)
    assert profile.source_profile == "news"
    assert profile.save_evidence is True
    mixed = NewsResearchSourceProfile(source_profile="mixed")
    assert mixed.source_profile == "mixed"


def test_news_source_functions_exist():
    assert collect_news_research_sources
    assert convert_news_items_to_evidence


def test_research_agent_source_profile_payloads():
    news_payload = ResearchAgentInput(query="AI", source_profile="news", news_budget={"max_total_items": 3})
    mixed_payload = ResearchAgentInput(query="AI", source_profile="mixed")
    assert news_payload.source_profile == "news"
    assert mixed_payload.source_profile == "mixed"
    assert news_payload.news_budget["max_total_items"] == 3


def test_nexus_and_lumen_save_evidence_modes():
    nexus = NewsResearchSourceProfile(source_profile="news", save_evidence=True, include_personal_use_only=False)
    lumen = NewsResearchSourceProfile(source_profile="news", save_evidence=False, include_personal_use_only=True)
    assert nexus.save_evidence is True
    assert lumen.save_evidence is False


def test_run_news_mvp_uses_news_source_layer():
    names = set(run_news_mvp.__code__.co_names)
    assert "NewsResearchSourceProfile" in names
    assert "collect_news_research_sources" in names
    assert "convert_news_items_to_evidence" in names
