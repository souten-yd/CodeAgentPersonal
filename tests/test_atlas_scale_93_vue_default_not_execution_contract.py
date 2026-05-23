import json
from pathlib import Path


def test_vue_defaultization_not_execution_enable_and_backend_authority() -> None:
    manifest = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    assert manifest['vue_next_default_enabled'] is True
    assert manifest['vue_next_default_not_execution_enable'] is True
    assert manifest['vue_next_default_execution_enabled'] is False
    assert manifest['vue_next_default_autonomous_enabled'] is False
    assert manifest['vue_next_default_backend_authoritative'] is True
    assert manifest['runtime_level'] == 'level_0_manual_only'
    assert manifest['autonomous_execution_enabled'] is False
    assert manifest['level1_execution_enabled'] is False
