from pathlib import Path

import pytest

from app.api.jobs import (
    LumenSearchBudget,
    clamp_lumen_search_budget,
    normalize_lumen_search_policy,
    resolve_lumen_search_policy,
)


DOC_PATH = Path("docs/lumen_design.md")


def test_lumen_search_budget_exists_with_defaults():
    budget = LumenSearchBudget()
    assert budget.max_queries == 3
    assert budget.max_results_per_query == 5
    assert budget.max_fetch_pages == 3
    assert budget.max_total_chars == 12000
    assert budget.timeout_sec == 20


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


@pytest.mark.parametrize("policy", ["off", "auto", "on"])
def test_search_policy_accepts_only_lumen_values(policy):
    assert normalize_lumen_search_policy(policy) == policy


@pytest.mark.parametrize("policy", ["recursive", "deep", "research", ""])
def test_search_policy_rejects_non_lumen_values(policy):
    with pytest.raises(ValueError, match="unsupported_lumen_search_policy"):
        normalize_lumen_search_policy(policy)


def test_search_enabled_compatibility_overrides_policy():
    assert resolve_lumen_search_policy(False, "on") == "off"
    assert resolve_lumen_search_policy(True, "off") == "on"
    assert resolve_lumen_search_policy(None, "auto") == "auto"


def test_lumen_docs_separate_lightweight_web_from_nexus_recursive_research():
    text = DOC_PATH.read_text(encoding="utf-8")
    assert "recursive depth = 0" in text
    assert "one-shot lightweight web assist" in text
    assert "Nexus" in text
    assert "Deep Research" in text
    assert "Recursive Research" in text
    assert "Lumen does not own recursive research" in text
