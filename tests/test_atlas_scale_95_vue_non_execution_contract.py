from pathlib import Path


def test_scale_95_vue_endpoint_set_remains_read_only_plus_plan_pool_post() -> None:
    text = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8')
    assert '/api/atlas/workflow-state/read-only' in text
    assert '/api/atlas/plan-pools' in text
    forbidden = ['/dry-run', '/execute', '/apply', '/approve', '/verify', '/rollback', '/retry', '/continue']
    for fragment in forbidden:
        assert fragment not in text
