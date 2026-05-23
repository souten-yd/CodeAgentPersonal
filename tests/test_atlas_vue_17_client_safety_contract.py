from pathlib import Path


def test_create_plan_pool_request_does_not_expose_unsafe_overrides_and_payload_is_hardcoded_safe() -> None:
    text = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8')

    create_request_block = text.split('export type CreatePlanPoolRequest = {', 1)[1].split('}', 1)[0]
    assert 'automation_level' not in create_request_block
    assert 'execution_strategy' not in create_request_block

    assert "automation_level: 'plan_then_ask'" in text
    assert "execution_strategy: 'sequential'" in text
    assert 'request.automation_level' not in text
    assert 'request.execution_strategy' not in text


def test_vue_client_calls_only_safe_endpoints_and_avoids_forbidden_execution_endpoints() -> None:
    text = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8')

    assert "fetch('/api/atlas/workflow-state/read-only'" in text
    assert "fetch('/api/atlas/plan-pools'" in text

    forbidden = [
        '/safe-apply/execute',
        '/auto-safe-apply',
        '/auto-safe-apply-and-verify',
        '/patch-proposals/generate',
        '/patch-proposals/decide',
        '/change-snapshots/restore',
        '/approvals/decide',
        '/automation/',
        '/execute',
        '/apply',
        '/approve',
        '/rollback',
        '/restore',
        '/verify',
        '/retry',
        '/continue',
    ]
    for item in forbidden:
        assert item not in text
