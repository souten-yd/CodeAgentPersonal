import json
from pathlib import Path


def test_vue_07_manifest_contract() -> None:
    m = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    assert m['vue_next_get_adapter_decision'] == 'connected_safe_get'
    assert m['vue_next_backend_get_adapter_connected'] is True
    assert m['vue_next_backend_contract_ready'] is True
    assert m['vue_next_workflow_state_contract'] == 'atlas.workflow_state.v1'
    assert m['vue_next_workflow_state_get_endpoint'] == '/api/atlas/workflow-state/read-only'
    assert m['vue_next_static_mount_decision'] in {'deferred_until_dist_policy_smoke', 'deferred_until_guarded_smoke_route', 'mounted_guarded_static_dist'}
    assert m['vue_next_route'] in {'', '/atlas-next'}
    assert isinstance(m['vue_next_route_mounted'], bool)
    assert m['vue_next_default_enabled'] is False
    assert m['vue_next_execution_enabled'] is False
    assert m['vue_next_source_of_truth'] is False
    assert m['vue_next_backend_authoritative'] is True
    assert m['vue_next_mutation_endpoints_enabled'] is False
    assert m['vue_next_action_buttons_enabled'] is False
    assert m['vue_next_available_actions_metadata_only'] is True
    assert m['level1_execution_enabled'] is False
    assert m['autonomous_execution_enabled'] is False
    assert m['vue_next_read_only_parity_hardened'] is True
    assert m['vue_next_visual_refinement_checkpoint'] == 'PR-ATLAS-VUE-07'
