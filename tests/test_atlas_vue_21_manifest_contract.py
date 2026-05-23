import json
from pathlib import Path

def test_manifest_has_vue21_default_enable_fields() -> None:
    m = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    assert m['vue_next_default_enable_checkpoint'] == 'PR-ATLAS-VUE-21'
    assert m['vue_next_default_enabled'] is True
    assert m['vue_next_default_route'] == '/'
    assert m['vue_next_default_fail_closed'] is True
    assert m['vue_next_default_execution_enabled'] is False
    assert m['vue_next_default_runtime_level'] == 'level_0_manual_only'
