import json
from pathlib import Path


def test_vue_06_manifest_contract() -> None:
    manifest = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    assert manifest['vue_next_get_adapter_decision'] == 'connected_safe_get'
    assert manifest['vue_next_backend_get_adapter_connected'] is True
    assert manifest['vue_next_backend_contract_ready'] is True
    assert manifest['vue_next_workflow_state_contract'] == 'atlas.workflow_state.v1'
    assert manifest['vue_next_workflow_state_contract_defined'] is True
    assert manifest['vue_next_workflow_state_get_endpoint'] == '/api/atlas/workflow-state/read-only'
    assert manifest['vue_next_static_mount_decision'] == 'deferred_until_dist_policy_smoke'
    assert manifest['vue_next_route'] == ''
    assert manifest['vue_next_route_mounted'] is False
    assert manifest['vue_next_default_enabled'] is False
    assert manifest['vue_next_execution_enabled'] is False
    assert manifest['vue_next_source_of_truth'] is False
    assert manifest['vue_next_backend_authoritative'] is True
    assert manifest['vue_next_mutation_endpoints_enabled'] is False
    assert manifest['vue_next_action_buttons_enabled'] is False
    assert manifest['vue_next_available_actions_metadata_only'] is True
    assert manifest['level1_execution_enabled'] is False
    assert manifest['autonomous_execution_enabled'] is False
