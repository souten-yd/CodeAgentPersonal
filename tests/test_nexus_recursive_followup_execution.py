from contextlib import ExitStack
from unittest.mock import patch

from app.nexus.research_agent import ResearchAgentInput, compute_recursive_download_budget, resolve_research_phase, run_research_job


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


def _base_recursive_mocks():
    return [
        patch('app.nexus.research_agent.plan_web_queries', return_value=['q']),
        patch('app.nexus.research_agent._generate_followup_queries', return_value=['followup query']),
        patch('app.nexus.research_agent._build_evidence_from_sources', return_value=[]),
        patch('app.nexus.research_agent.save_evidence_items', return_value=0),
        patch('app.nexus.research_agent.replace_evidence_items_for_job', return_value=0),
        patch('app.nexus.research_agent._load_source_chunks', return_value=[]),
        patch('app.nexus.research_agent.build_citation_map', return_value=[]),
        patch('app.nexus.research_agent.build_answer_payload', return_value={'answer': 'ok'}),
    ]


def test_case_a_recursive_followup_executes_search_for_unresolved_low_confidence():
    with ExitStack() as stack:
        mocked_search = stack.enter_context(patch('app.nexus.research_agent.run_web_search', return_value={'items': [{'url': 'https://example.com/followup'}]}))
        stack.enter_context(patch('app.nexus.research_agent._download_sources_parallel', side_effect=[([{'source_id': 'src-seed', 'url': 'https://example.com/seed', 'status': 'downloaded', 'size': 10}], 0), ([{'source_id': 'src-followup', 'url': 'https://example.com/followup', 'status': 'downloaded', 'size': 10}], 0)]))
        stack.enter_context(patch('app.nexus.research_agent.register_or_update_sources', side_effect=[[{'source_id': 'src-seed', 'url': 'https://example.com/seed'}], [{'source_id': 'src-followup', 'url': 'https://example.com/followup'}]]))
        stack.enter_context(patch('app.nexus.research_agent._analyze_research_gaps', return_value={'confidence': 0.49, 'gaps': ['missing_support'], 'unresolved_items': ['x']}))
        stack.enter_context(patch('app.nexus.research_agent.collect_source_candidates', return_value=[{'url': 'https://example.com/followup'}]))
        stack.enter_context(patch('app.nexus.research_agent.rank_source_candidates', return_value=[{'url': 'https://example.com/followup'}]))
        for m in _base_recursive_mocks():
            stack.enter_context(m)
        result = run_research_job(ResearchAgentInput(query='q', recursive_search=True, max_iterations=2, confidence_threshold=0.7), job_id='job-case-a')
    answer = result['answer']
    assert mocked_search.call_count >= 2
    assert answer['followup_searches_executed'] >= 1
    assert answer['recursive_stop_reason'] != 'download_budget_exhausted'
    assert answer['recursive_download_budget_remaining'] == answer['recursive_reserved_downloads'] - answer['recursive_download_attempt_count']


def test_case_b_search_only_followup_executes_without_download_budget():
    with ExitStack() as stack:
        mocked_search = stack.enter_context(patch('app.nexus.research_agent.run_web_search', return_value={'items': [{'url': 'https://example.com/followup'}]}))
        mocked_download = stack.enter_context(patch('app.nexus.research_agent._download_sources_parallel', side_effect=[([{'source_id': 'src-seed', 'url': 'https://example.com/seed', 'status': 'downloaded', 'size': 10}], 0)]))
        stack.enter_context(patch('app.nexus.research_agent.register_or_update_sources', side_effect=[[{'source_id': 'src-seed', 'url': 'https://example.com/seed'}], []]))
        stack.enter_context(patch('app.nexus.research_agent._analyze_research_gaps', return_value={'confidence': 0.49, 'gaps': ['missing_support'], 'unresolved_items': ['x']}))
        stack.enter_context(patch('app.nexus.research_agent.collect_source_candidates', return_value=[{'url': 'https://example.com/followup'}]))
        stack.enter_context(patch('app.nexus.research_agent.rank_source_candidates', return_value=[{'url': 'https://example.com/followup'}]))
        for m in _base_recursive_mocks():
            stack.enter_context(m)
        result = run_research_job(ResearchAgentInput(query='q', recursive_search=True, max_iterations=2, confidence_threshold=0.7, max_downloads=0), job_id='job-case-b')
    answer = result['answer']
    assert mocked_download.call_count == 1
    assert mocked_search.call_count >= 2
    assert answer['followup_searches_executed'] >= 1
    assert answer['recursive_stop_reason'] == 'search_only_followup'
    assert answer['recursive_followup_skip_reason'] == 'download_budget_no_download_allowed'


def test_case_c_duplicate_followup_sources_still_counts_search_execution():
    with ExitStack() as stack:
        stack.enter_context(patch('app.nexus.research_agent.run_web_search', return_value={'items': [{'url': 'https://example.com/seed'}]}))
        stack.enter_context(patch('app.nexus.research_agent._download_sources_parallel', return_value=([{'source_id': 'src-seed', 'url': 'https://example.com/seed', 'status': 'downloaded', 'size': 10}], 0)))
        stack.enter_context(patch('app.nexus.research_agent.register_or_update_sources', return_value=[{'source_id': 'src-seed', 'url': 'https://example.com/seed', 'final_url': 'https://example.com/seed'}]))
        stack.enter_context(patch('app.nexus.research_agent._analyze_research_gaps', return_value={'confidence': 0.2, 'gaps': ['missing_support'], 'unresolved_items': ['x']}))
        stack.enter_context(patch('app.nexus.research_agent.collect_source_candidates', return_value=[{'url': 'https://example.com/seed'}]))
        stack.enter_context(patch('app.nexus.research_agent.rank_source_candidates', return_value=[{'url': 'https://example.com/seed'}]))
        for m in _base_recursive_mocks():
            stack.enter_context(m)
        result = run_research_job(ResearchAgentInput(query='q', mode='deep', depth='deep', recursive_search=True, max_iterations=2, max_downloads=20), job_id='job-case-c')
    answer = result['answer']
    assert answer['followup_queries_generated'] > 0
    assert answer['followup_searches_executed'] >= 1
    assert answer['added_sources_total'] == 0
    assert answer['recursive_stop_reason'] in {'no_new_followup_sources', 'duplicate_followup_sources'}


def test_case_d_sufficient_confidence_skips_unnecessary_followup():
    with ExitStack() as stack:
        mocked_search = stack.enter_context(patch('app.nexus.research_agent.run_web_search', return_value={'items': [{'url': 'https://example.com/seed'}]}))
        stack.enter_context(patch('app.nexus.research_agent._download_sources_parallel', return_value=([{'source_id': 'src-seed', 'url': 'https://example.com/seed', 'status': 'downloaded', 'size': 10}], 0)))
        stack.enter_context(patch('app.nexus.research_agent.register_or_update_sources', return_value=[{'source_id': 'src-seed', 'url': 'https://example.com/seed'}]))
        stack.enter_context(patch('app.nexus.research_agent._analyze_research_gaps', return_value={'confidence': 0.9, 'sufficient': True, 'gaps': [], 'unresolved_items': []}))
        stack.enter_context(patch('app.nexus.research_agent.collect_source_candidates', return_value=[{'url': 'https://example.com/followup'}]))
        stack.enter_context(patch('app.nexus.research_agent.rank_source_candidates', return_value=[{'url': 'https://example.com/followup'}]))
        for m in _base_recursive_mocks():
            stack.enter_context(m)
        result = run_research_job(ResearchAgentInput(query='q', recursive_search=True, max_iterations=2, confidence_threshold=0.7), job_id='job-case-d')
    answer = result['answer']
    assert answer['recursive_stop_reason'] in {'sufficient_confidence', 'confidence_threshold_reached', 'sufficient_evidence'}
    assert answer['followup_searches_executed'] == 0
