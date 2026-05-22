import json
from pathlib import Path


def test_vue16_manifest_fields() -> None:
    m = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    assert m['vue_next_requirement_input_checkpoint'] == 'PR-ATLAS-VUE-16'
    assert m['vue_next_start_atlas_endpoint'] == '/api/atlas/plan-pools'
    assert m['vue_next_start_atlas_method'] == 'POST'
    assert m['vue_next_start_atlas_scope'] == 'planning_metadata_only'
    assert m['vue_next_plan_pool_creation_execution_enabled'] is False
    assert m['vue_next_post_plan_execution_enabled'] is False
    assert m['vue_next_start_atlas_auto_execute'] is False
    assert m['vue_next_action_buttons_enabled'] is False
    assert m['runtime_level'] == 'level_0_manual_only'
    assert m['vue_next_execution_enabled'] is False
    assert m['vue_next_workflow_state_real_data_connection_status'] == 'schema_ready_safe_if_available'
