from app.api.nexus import NexusResearchRunRequest


def _field_names(model_type):
    if hasattr(model_type, "model_fields"):
        return set(model_type.model_fields)
    return set(model_type.__fields__)


def test_nexus_research_run_request_restores_source_profile_contract_defaults():
    fields = _field_names(NexusResearchRunRequest)

    assert "source_profile" in fields
    assert "news_budget" in fields

    payload = NexusResearchRunRequest(query="market news")

    assert payload.source_profile == "web"
    assert payload.news_budget is None


def test_nexus_research_run_request_preserves_news_profile_and_budget():
    budget = {"max_total_items": 12}

    payload = NexusResearchRunRequest(
        query="market news",
        source_profile="news",
        news_budget=budget,
    )

    assert payload.source_profile == "news"
    assert payload.news_budget == budget
