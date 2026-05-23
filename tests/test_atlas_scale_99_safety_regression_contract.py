from pathlib import Path


def test_no_level1_execution_route_exposed_in_vue_readiness_panel_or_client():
    panel = Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text(encoding='utf-8')
    client = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8')
    merged = panel + '\n' + client
    for endpoint in ['/api/atlas/level1/execute', '/dry-run', '/approve', '/apply', '/rollback', '/retry', '/continue']:
        assert endpoint not in merged
