import json
from pathlib import Path


def test_runtime_and_execution_safety_regression_and_debug_test_registration():
    manifest = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    assert manifest['runtime_level'] == 'level_0_manual_only'
    assert manifest['level1_execution_enabled'] is False
    assert manifest['autonomous_execution_enabled'] is False
    assert manifest['level1_readiness_ui_uses_get_only'] is True
    assert 'desktop_lumen_input_visible' in Path('scripts/run_debug_test_matrix.py').read_text(encoding='utf-8')
