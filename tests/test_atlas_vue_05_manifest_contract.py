from pathlib import Path
import json


def test_vue_05_manifest_contract_flags() -> None:
    manifest = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))

    assert manifest['vue_next_workflow_state_contract'] == 'atlas.workflow_state.v1'
    assert manifest['vue_next_workflow_state_contract_defined'] is True
    assert manifest['vue_next_workflow_state_get_endpoint'] == '/api/atlas/workflow-state/read-only'
    assert manifest['vue_next_backend_contract_ready'] is True
    assert manifest['vue_next_get_adapter_decision'] == 'contract_defined_binding_deferred'
    assert manifest['vue_next_backend_get_adapter_connected'] is False

    assert manifest['vue_next_static_mount_decision'] == 'deferred_no_dist_strategy'
    assert manifest['vue_next_route'] == ''
    assert manifest['vue_next_route_mounted'] is False
    assert manifest['vue_next_default_enabled'] is False
    assert manifest['vue_next_execution_enabled'] is False
    assert manifest['vue_next_source_of_truth'] is False
    assert manifest['vue_next_backend_authoritative'] is True
    assert manifest['vue_next_mutation_endpoints_enabled'] is False
    assert manifest['vue_next_action_buttons_enabled'] is False
    assert manifest['vue_next_available_actions_metadata_only'] is True
