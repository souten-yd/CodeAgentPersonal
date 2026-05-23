import json
from pathlib import Path

def test_scale_97_runtime_and_execution_safety_unchanged() -> None:
    m=json.loads(Path('web/atlas_ui_surface_manifest.json').read_text())
    assert m['runtime_level']=='level_0_manual_only'
    assert m['autonomous_execution_enabled'] is False
    assert m['level1_execution_enabled'] is False
    assert m['level1_callable_execution_endpoint_enabled'] is False
