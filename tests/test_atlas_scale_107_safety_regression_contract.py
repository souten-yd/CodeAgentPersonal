import json
from pathlib import Path
MANIFEST=json.loads(Path('web/atlas_ui_surface_manifest.json').read_text())
CSS=Path('web/css/app.css').read_text()
def test_runtime_execution_flags_still_disabled():
    assert MANIFEST['runtime_level']=='level_0_manual_only'
    assert MANIFEST['level1_execution_enabled'] is False
    assert MANIFEST['autonomous_execution_enabled'] is False
def test_desktop_grid_layout_tokens_preserved():
    assert 'display:grid' in CSS
    assert 'grid-template-columns' in CSS
