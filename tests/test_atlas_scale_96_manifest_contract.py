import json
from pathlib import Path

def test_scale_96_manifest_fields() -> None:
    m=json.loads(Path('web/atlas_ui_surface_manifest.json').read_text())
    assert m['level1_gate_source_mapping_checkpoint']=='PR-ATLAS-SCALE-96'
    assert m['level1_gate_source_mapping_enabled'] is True
    assert m['level1_gate_source_mapping_metadata_only'] is True
    assert m['level1_gate_source_mapping_mutation_enabled'] is False
    assert m['level1_gate_source_mapping_execution_enabled'] is False
