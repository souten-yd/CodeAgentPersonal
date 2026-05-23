import json
from pathlib import Path


def test_manifest_has_vue21_final_defaultization_fields() -> None:
    manifest = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))

    expected = {
        'vue_next_default_enable_checkpoint': 'PR-ATLAS-VUE-21',
        'vue_next_default_enabled': True,
        'vue_next_current_default_route': '/',
        'vue_next_previous_default_route': 'ui.html',
        'vue_next_legacy_ui_available': True,
        'vue_next_legacy_ui_route': '/ui/',
        'vue_next_ui_html_legacy_available': True,
        'vue_next_default_requires_valid_dist': True,
        'vue_next_default_fail_closed': True,
        'vue_next_default_fallback_to_legacy_ui': True,
        'vue_next_default_serves_raw_source': False,
        'vue_next_default_execution_enabled': False,
        'vue_next_default_autonomous_enabled': False,
        'vue_next_default_backend_authoritative': True,
        'vue_next_default_runtime_level': 'level_0_manual_only',
        'vue_next_default_switch_scope': 'guarded_default_route_only',
        'vue_next_default_not_execution_enable': True,
        'vue_next_after_defaultization_returns_to_automation_track': 'PR-ATLAS-SCALE-93',
        'vue_next_vue20_previous_default_route': 'ui.html',
    }
    for key, value in expected.items():
        assert manifest.get(key) == value

    assert manifest['vue_next_execution_enabled'] is False
    assert manifest['vue_next_mutation_endpoints_enabled'] is False
    assert manifest['vue_next_action_buttons_enabled'] is False
    assert manifest['level1_execution_enabled'] is False
    assert manifest['autonomous_execution_enabled'] is False
    assert manifest['runtime_level'] == 'level_0_manual_only'
