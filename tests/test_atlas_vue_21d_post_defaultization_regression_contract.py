from pathlib import Path
import json


def test_vue_21d_post_defaultization_manifest_contract() -> None:
    m = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    assert m['vue_next_default_enabled'] is True
    assert m['vue_next_current_default_route'] == '/'
    assert m['vue_next_previous_default_route'] == 'ui.html'
    assert m['vue_next_default_requires_valid_dist'] is True
    assert m['vue_next_default_fail_closed'] is True
    assert m['vue_next_default_fallback_to_legacy_ui'] is True
    assert m['vue_next_default_serves_raw_source'] is False
    assert m['vue_next_default_execution_enabled'] is False
    assert m['vue_next_default_autonomous_enabled'] is False
    assert m['runtime_level'] == 'level_0_manual_only'
    assert m['level1_execution_enabled'] is False
    assert m['autonomous_execution_enabled'] is False


def test_vue_21d_post_defaultization_client_endpoint_contract() -> None:
    client = Path('web/atlas-next/src/api/atlasClient.ts').read_text(encoding='utf-8')
    assert "fetch('/api/atlas/workflow-state/read-only', { method: 'GET' })" in client
    assert "fetch('/api/atlas/plan-pools'" in client

    forbidden_tokens = [
        '/dry-run', '/execute', '/apply', '/approve', '/rollback', '/restore', '/verify', '/retry', '/continue'
    ]
    for token in forbidden_tokens:
        assert token not in client
