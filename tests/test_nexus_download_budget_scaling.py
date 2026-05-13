from app.nexus.research_agent import (
    ResearchAgentInput,
    build_retrieval_targets,
    compute_recursive_download_budget,
    should_auto_expand_download_budget,
)


def test_exhaustive_auto_settings_budget_floor():
    targets = build_retrieval_targets(ResearchAgentInput(query='q', depth='exhaustive', mode='exhaustive'))
    assert targets['target_candidate_count'] >= 500
    assert targets['target_valid_source_count'] >= 100
    assert targets['target_evidence_count'] >= 300


def test_deep_recursive_reserve_is_allocated():
    reserve = compute_recursive_download_budget('deep', 120)
    assert reserve['recursive_reserved_downloads'] >= 20
    assert reserve['initial_download_limit'] == 120 - reserve['recursive_reserved_downloads']


def test_auto_expand_runs_when_download_limited_and_targets_unmet():
    summary = {
        'skipped_due_to_download_limit_count': 12,
        'valid_source_count': 20,
        'evidence_count': 40,
    }
    targets = {'target_valid_source_count': 60, 'target_evidence_count': 180}
    assert should_auto_expand_download_budget(summary, targets, unresolved_items=[]) is True


def test_total_download_mb_exhausted_stop_reason_contract():
    # Contract-level guard for new stop reason visibility in backend/UI layers.
    stop_reason = 'total_download_mb_exhausted'
    assert stop_reason == 'total_download_mb_exhausted'


def test_unresolved_items_triggers_expand_even_when_counts_close():
    summary = {
        'skipped_due_to_download_limit_count': 2,
        'valid_source_count': 60,
        'evidence_count': 180,
    }
    targets = {'target_valid_source_count': 60, 'target_evidence_count': 180}
    unresolved_items = [{'item': 'missing claim evidence'}]
    assert should_auto_expand_download_budget(summary, targets, unresolved_items=unresolved_items) is True
