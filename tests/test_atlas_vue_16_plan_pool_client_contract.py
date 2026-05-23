from pathlib import Path


def test_vue16_plan_pool_client_only_allowed_post() -> None:
    text = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8')
    assert "fetch('/api/atlas/plan-pools'" in text
    assert "method: 'POST'" in text
    assert "automation_level: 'plan_then_ask'" in text
    assert "execution_strategy: 'sequential'" in text

    for blocked in [
        '/safe-apply/execute', '/auto-safe-apply', '/auto-safe-apply-and-verify',
        '/patch-proposals/generate', '/patch-proposals/decide', '/change-snapshots/restore',
        '/approvals/decide', '/automation/', '/execute', '/apply', '/approve',
        '/rollback', '/restore', '/verify', '/retry', '/continue'
    ]:
        assert blocked not in text
