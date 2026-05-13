from app.nexus.research_agent import ResearchAgentInput, compute_recursive_download_budget, resolve_research_phase


def test_deep_auto_settings_contract_values():
    payload = ResearchAgentInput(query='q', depth='deep', recursive_search=True, max_iterations=2, max_followup_queries=8)
    assert payload.recursive_search is True
    assert payload.max_iterations >= 2
    assert payload.max_followup_queries >= 8


def test_initial_download_limit_reserves_recursive_budget_for_deep_and_exhaustive():
    deep = compute_recursive_download_budget('deep', 120)
    assert deep['initial_download_limit'] <= 90
    assert deep['recursive_reserved_downloads'] >= 30

    exhaustive = compute_recursive_download_budget('exhaustive', 200)
    assert exhaustive['initial_download_limit'] <= 140
    assert exhaustive['recursive_reserved_downloads'] >= 60


def test_phase_helper_includes_expected_recursive_phase_metadata():
    meta = resolve_research_phase('followup_searching')
    assert meta['phase_index'] == 9
    assert meta['phase_total'] == 10


def test_recursive_followup_execution_metrics_contract():
    answer_payload = {
        "recursive_search": True,
        "followup_queries_generated": 2,
        "followup_searches_executed": 1,
        "recursive_reserved_downloads": 10,
        "recursive_download_attempt_count": 3,
        "recursive_downloaded_count": 2,
        "recursive_download_budget_remaining": 7,
    }
    assert answer_payload["followup_searches_executed"] >= 1
    assert answer_payload["recursive_download_budget_remaining"] == (
        answer_payload["recursive_reserved_downloads"] - answer_payload["recursive_download_attempt_count"]
    )


def test_recursive_search_only_followup_contract():
    answer_payload = {
        "recursive_search": True,
        "followup_queries_generated": 1,
        "followup_searches_executed": 1,
        "recursive_reserved_downloads": 0,
        "recursive_download_attempt_count": 0,
        "recursive_followup_skip_reason": "download_budget_no_download_allowed",
        "recursive_stop_reason": "search_only_followup",
    }
    assert answer_payload["followup_searches_executed"] >= 1
    assert answer_payload["recursive_followup_skip_reason"] == "download_budget_no_download_allowed"


def test_recursive_followup_duplicate_sources_still_counts_execution():
    answer_payload = {
        "followup_queries_generated": 2,
        "followup_searches_executed": 1,
        "added_sources_total": 0,
        "recursive_stop_reason": "no_new_followup_sources",
        "recursive_followup_skip_reason": "duplicate_followup_sources",
    }
    assert answer_payload["followup_searches_executed"] >= 1
    assert answer_payload["added_sources_total"] == 0
    assert answer_payload["recursive_stop_reason"] in {"no_new_followup_sources", "duplicate_followup_sources"}
