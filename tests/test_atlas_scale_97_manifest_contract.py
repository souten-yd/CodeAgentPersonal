import json
from pathlib import Path


def test_scale_97_manifest_fields() -> None:
    m = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text())
    assert m['level1_readiness_ui_checkpoint'] == 'PR-ATLAS-SCALE-97'
    assert m['level1_readiness_ui_enabled'] is True
    assert m['level1_readiness_ui_display_only'] is True
    assert m['level1_readiness_ui_uses_get_only'] is True
    assert m['level1_readiness_ui_execution_controls_enabled'] is False
    assert m['level1_readiness_ui_mutation_controls_enabled'] is False
