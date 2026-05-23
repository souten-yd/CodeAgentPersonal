import json
from pathlib import Path


def test_vue21_safety_regression_contract() -> None:
    manifest = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))

    assert manifest['vue_next_legacy_ui_route'] == '/ui/'
    assert manifest['vue_next_default_execution_enabled'] is False
    assert manifest['vue_next_default_autonomous_enabled'] is False
    assert manifest['vue_next_default_backend_authoritative'] is True
    assert manifest['vue_next_default_runtime_level'] == 'level_0_manual_only'

    methods_and_paths = {
        ('GET', manifest['vue_next_workflow_state_get_endpoint']),
        (manifest['vue_next_start_atlas_method'], manifest['vue_next_start_atlas_endpoint']),
    }
    assert methods_and_paths == {
        ('GET', '/api/atlas/workflow-state/read-only'),
        ('POST', '/api/atlas/plan-pools'),
    }

    forbidden_fragments = [
        '/dry-run', '/execute', '/apply', '/approve', '/rollback', '/restore', '/verify', '/retry', '/continue',
    ]
    for _method, path in methods_and_paths:
        for fragment in forbidden_fragments:
            assert fragment not in path
