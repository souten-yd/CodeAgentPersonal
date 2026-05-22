from fastapi.testclient import TestClient

from app.server import create_app


def test_preview_diagnostics_get_only_and_metadata() -> None:
    app = create_app()
    client = TestClient(app)

    res = client.get('/api/atlas/vue-next-preview/diagnostics')
    assert res.status_code == 200
    payload = res.json()

    expected_keys = {
        'route_mounted', 'route_path', 'dist_dir', 'dist_exists', 'dist_validation_result',
        'index_present', 'asset_count', 'fallback_ready', 'preview_health_state',
        'raw_source_serving_allowed', 'default_route', 'ui_html_fallback', 'root_fallback',
        'read_only', 'backend_authoritative', 'mutation_endpoints_enabled', 'execution_enabled'
    }
    assert expected_keys.issubset(payload.keys())
    assert payload['route_path'] == '/atlas-next'
    assert payload['read_only'] is True
    assert payload['backend_authoritative'] is True
    assert payload['mutation_endpoints_enabled'] is False
    assert payload['execution_enabled'] is False
    assert payload['raw_source_serving_allowed'] is False
    assert payload['default_route'] is False
    assert payload['ui_html_fallback'] is False
    assert payload['root_fallback'] is False


def test_preview_diagnostics_route_is_get_only() -> None:
    app = create_app()
    client = TestClient(app)
    for method in ('post', 'put', 'patch', 'delete'):
        res = getattr(client, method)('/api/atlas/vue-next-preview/diagnostics')
        assert res.status_code == 405
