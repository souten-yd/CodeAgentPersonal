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
