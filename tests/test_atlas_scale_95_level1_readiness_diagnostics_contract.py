from fastapi.testclient import TestClient

from main import app


def test_scale_95_level1_readiness_get_only_metadata_contract() -> None:
    client = TestClient(app)
    response = client.get('/api/atlas/level1/readiness')
    assert response.status_code == 200
    payload = response.json()
    assert payload['enabled'] is False
    assert payload['runtime_level'] == 'level_0_manual_only'
    assert payload['level1_execution_enabled'] is False
    assert payload['backend_skeleton_enabled'] is True
    assert payload['callable_execution_endpoint_enabled'] is False
    assert payload['vue_execution_controls_enabled'] is False
    assert payload['dry_run_required'] is True
    assert payload['explicit_approval_required'] is True
    assert payload['single_action_only_required'] is True
    assert isinstance(payload.get('required_gates'), list) and payload['required_gates']
    assert isinstance(payload.get('blockers'), list) and payload['blockers']
