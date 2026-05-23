from pathlib import Path
import json

def test_manifest_contains_vue20_readiness_fields() -> None:
    m = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    assert m['vue_next_default_readiness_checkpoint'] == 'PR-ATLAS-VUE-20'
    assert m['vue_next_default_readiness_preflight_enabled'] is True
    assert m['vue_next_default_readiness_display_only'] is True
    assert m['vue_next_default_switch_enabled'] is False
    assert m['vue_next_default_enable_checkpoint'] == 'PR-ATLAS-VUE-21'
    assert m['vue_next_current_default_route'] == '/'
    assert m['vue_next_default_switch_scope'] == 'guarded_default_route_only'
    assert m['vue_next_default_execution_enabled'] is False
    assert m['runtime_level'] == 'level_0_manual_only'
    assert m['vue_next_execution_enabled'] is False
    assert m['runtime_level'] == 'level_0_manual_only'
