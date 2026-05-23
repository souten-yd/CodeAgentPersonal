import json
from pathlib import Path


def test_vue_11_manifest_observability_contract() -> None:
    m = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    assert m['vue_next_preview_health'] == 'observable_fail_closed'
    assert m['vue_next_preview_dist_detected'] in (True, False, 'runtime_detected')
    assert m['vue_next_preview_assets_detected'] in (True, False, 'runtime_detected')
    assert m['vue_next_preview_index_present'] in (True, False, 'runtime_detected')
    assert m['vue_next_preview_fallback_ready'] is True
    assert m['vue_next_preview_route_observable'] is True
    assert m['vue_next_preview_diagnostics_enabled'] is True
    assert m['vue_next_preview_diagnostics_endpoint'] == '/api/atlas/vue-next-preview/diagnostics'
    assert m['vue_next_default_enabled'] is True
    assert m['vue_next_default_not_execution_enable'] is True
    assert m['vue_next_execution_enabled'] is False
    assert m['runtime_level'] == 'level_0_manual_only'
    assert m['vue_next_execution_enabled'] is False
    assert m['vue_next_mutation_endpoints_enabled'] is False
    assert m['vue_next_action_buttons_enabled'] is False
    assert m['vue_next_backend_authoritative'] is True
    assert m['vue_next_source_of_truth'] is False
    assert m['runtime_level'] == 'level_0_manual_only'
    assert m['level1_execution_enabled'] is False
    assert m['autonomous_execution_enabled'] is False
