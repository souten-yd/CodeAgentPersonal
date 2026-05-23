from pathlib import Path

from fastapi.testclient import TestClient

from main import app


def test_scale_96b_readiness_safety_regression_contract() -> None:
    client = TestClient(app)
    get_response = client.get('/api/atlas/level1/readiness')
    assert get_response.status_code == 200
    payload = get_response.json()
    assert payload['mutation_performed'] is False
    assert payload['execution_performed'] is False
    assert payload['runtime_level'] == 'level_0_manual_only'
    assert payload['level1_execution_enabled'] is False
    assert payload['enabled'] is False

    for method in (client.post, client.put, client.patch, client.delete):
        response = method('/api/atlas/level1/readiness')
        assert response.status_code in (404, 405)


def test_scale_96b_no_level1_execute_routes_or_vue_execution_endpoints() -> None:
    api_sources = []
    for path in ('main.py', 'app/server.py', 'app/api/atlas_pipeline.py'):
        pp = Path(path)
        if pp.exists():
            api_sources.append(pp.read_text(encoding='utf-8'))
    assert api_sources
    assert '/api/atlas/level1/execute' not in '\n'.join(api_sources)

    vue_api = Path('web/js/atlas_pipeline_api.js').read_text(encoding='utf-8')
    vue_dashboard = Path('web/js/atlas_dashboard.js').read_text(encoding='utf-8')
    combined = f'{vue_api}\n{vue_dashboard}'
    for suffix in ('/execute', '/dry-run', '/apply', '/approve', '/rollback', '/restore', '/verify', '/retry', '/continue'):
        assert f'/api/atlas/level1{suffix}' not in combined
