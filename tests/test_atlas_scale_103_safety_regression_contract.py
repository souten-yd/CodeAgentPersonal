import json
from pathlib import Path
manifest=json.loads(Path('web/atlas_ui_surface_manifest.json').read_text())

def test_runtime_and_execution_safety_flags():
    assert manifest['runtime_level']=='level_0_manual_only'
    assert manifest['level1_execution_enabled'] is False
    assert manifest['autonomous_execution_enabled'] is False
    assert manifest['level1_readiness_ui_display_only'] is True
    assert manifest['level1_readiness_ui_uses_get_only'] is True
