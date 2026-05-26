from pathlib import Path

from app.atlas.workflow_state_contract import build_read_only_workflow_state


def test_workflow_state_builds_guarded_execution_review_from_backend_skeleton() -> None:
    payload = build_read_only_workflow_state(
        goal='g',
        project_path='p',
        phase='read_only_preview',
        status='ok',
        primary_cta_label='Read-only',
    )
    review = payload['guarded_execution_review']
    assert review['checkpoint'] == 'PR-ATLAS-SCALE-126'
    assert review['display_only'] is True
    assert review['backend_authoritative'] is True
    assert review['vue_authoritative'] is False
    assert review['requires_dry_run'] is True
    assert review['requires_approval'] is True
    assert review['requires_runtime_transition'] is True
    assert len(review['review_items']) <= 8
    assert all(set(item) == {'label', 'ready', 'source'} for item in review['review_items'])
    assert review['blocked_reasons']


def test_workflow_state_guarded_execution_review_never_enables_actions() -> None:
    payload = build_read_only_workflow_state(
        goal='g',
        project_path='p',
        phase='read_only_preview',
        status='ok',
        primary_cta_label='Read-only',
    )
    review = payload['guarded_execution_review']
    for key in [
        'callable_execution_route_enabled',
        'execution_enabled',
        'approval_action_enabled',
        'dry_run_action_enabled',
        'execute_action_enabled',
        'apply_action_enabled',
        'verify_action_enabled',
        'rollback_action_enabled',
        'retry_continue_action_enabled',
    ]:
        assert review[key] is False


def test_workflow_state_contract_source_uses_level1_skeleton_for_review() -> None:
    text = Path('app/atlas/workflow_state_contract.py').read_text(encoding='utf-8')
    assert 'Level1GuardedExecutionSkeleton.build_disabled_level1_contract()' in text
    assert '"guarded_execution_review": _build_guarded_execution_review()' in text
