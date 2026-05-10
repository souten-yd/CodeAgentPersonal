from pathlib import Path

from app.lumen.budgets import (
    LumenNewsBudget,
    LumenSearchBudget,
    LumenWeatherBudget,
    clamp_lumen_news_budget,
    clamp_lumen_search_budget,
    clamp_lumen_weather_budget,
    normalize_lumen_search_policy,
    normalize_lumen_tool_policy,
)

DOC_PATH = Path("docs/lumen_design.md")


def test_lumen_search_weather_news_budget_types_exist_with_defaults():
    search = LumenSearchBudget()
    assert search.max_queries == 3
    assert search.max_results_per_query == 5
    assert search.max_fetch_pages == 3
    assert search.max_total_chars == 12000
    assert search.timeout_sec == 20

    weather = LumenWeatherBudget()
    assert weather.max_geocoding_results == 3
    assert weather.forecast_days == 3
    assert weather.timeout_sec == 10

    news = LumenNewsBudget()
    assert news.max_providers == 3
    assert news.max_queries == 2
    assert news.max_results_per_provider == 5
    assert news.max_total_items == 15
    assert news.max_fetch_pages == 0
    assert news.timeout_sec == 20
    assert news.save_to_nexus is False


def test_lumen_search_budget_clamps_minimums_and_maximums():
    low = clamp_lumen_search_budget(
        {
            "max_queries": -1,
            "max_results_per_query": 0,
            "max_fetch_pages": -2,
            "max_total_chars": 100,
            "timeout_sec": 1,
        }
    )
    assert low.max_queries == 0
    assert low.max_results_per_query == 1
    assert low.max_fetch_pages == 0
    assert low.max_total_chars == 2000
    assert low.timeout_sec == 5

    high = clamp_lumen_search_budget(
        {
            "max_queries": 999,
            "max_results_per_query": 999,
            "max_fetch_pages": 999,
            "max_total_chars": 999999,
            "timeout_sec": 999,
        }
    )
    assert high.max_queries == 5
    assert high.max_results_per_query == 10
    assert high.max_fetch_pages == 5
    assert high.max_total_chars == 30000
    assert high.timeout_sec == 60


def test_lumen_weather_budget_clamps_minimums_and_maximums():
    low = clamp_lumen_weather_budget({"max_geocoding_results": 0, "forecast_days": 0, "timeout_sec": 1})
    assert low.max_geocoding_results == 1
    assert low.forecast_days == 1
    assert low.timeout_sec == 5

    high = clamp_lumen_weather_budget({"max_geocoding_results": 999, "forecast_days": 999, "timeout_sec": 999})
    assert high.max_geocoding_results == 5
    assert high.forecast_days == 7
    assert high.timeout_sec == 30


def test_lumen_news_budget_clamps_minimums_and_maximums():
    low = clamp_lumen_news_budget(
        {
            "max_providers": 0,
            "max_queries": 0,
            "max_results_per_provider": 0,
            "max_total_items": 0,
            "max_fetch_pages": -1,
            "timeout_sec": 1,
        }
    )
    assert low.max_providers == 1
    assert low.max_queries == 1
    assert low.max_results_per_provider == 1
    assert low.max_total_items == 3
    assert low.max_fetch_pages == 0
    assert low.timeout_sec == 5
    assert low.save_to_nexus is False

    high = clamp_lumen_news_budget(
        {
            "max_providers": 999,
            "max_queries": 999,
            "max_results_per_provider": 999,
            "max_total_items": 999,
            "max_fetch_pages": 999,
            "timeout_sec": 999,
            "save_to_nexus": True,
        }
    )
    assert high.max_providers == 5
    assert high.max_queries == 5
    assert high.max_results_per_provider == 10
    assert high.max_total_items == 30
    assert high.max_fetch_pages == 3
    assert high.timeout_sec == 60
    assert high.save_to_nexus is True


def test_tool_and_search_policy_are_limited_to_off_auto_on_with_auto_fallback():
    for policy in ["off", "auto", "on"]:
        assert normalize_lumen_tool_policy(policy) == policy
        assert normalize_lumen_search_policy(policy) == policy

    for policy in ["recursive", "deep", "research", "", None]:
        assert normalize_lumen_tool_policy(policy) == "auto"
        assert normalize_lumen_search_policy(policy) == "auto"


def test_lumen_budget_models_do_not_include_recursive_depth():
    for model in [LumenSearchBudget, LumenWeatherBudget, LumenNewsBudget]:
        fields = model.model_fields if hasattr(model, "model_fields") else model.__fields__
        assert "recursive_depth" not in fields
        assert "max_depth" not in fields


def test_lumen_docs_separate_lightweight_web_from_nexus_recursive_research():
    text = DOC_PATH.read_text(encoding="utf-8")
    assert "recursive depth = 0" in text
    assert "one-shot lightweight web assist" in text
    assert "Nexus" in text
    assert "Deep Research" in text
    assert "Recursive Research" in text
    assert "Lumen does not own recursive research" in text
    assert "must not mix Nexus Deep Research controls into Lumen budgets" in text
