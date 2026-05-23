from pathlib import Path


def test_vue_still_only_uses_read_only_and_plan_pool_endpoints() -> None:
    content = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8')
    assert '/api/atlas/workflow-state/read-only' in content
    assert '/api/atlas/plan-pools' in content
    forbidden = ['/dry-run', '/execute', '/apply', '/approve', '/rollback', '/restore', '/verify', '/retry', '/continue']
    for item in forbidden:
        assert item not in content
