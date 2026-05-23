import json
from pathlib import Path

def test_manifest_scale_101_history_fields_present_and_safe():
    m = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    assert m['level1_readiness_metadata_history_checkpoint'] == 'PR-ATLAS-SCALE-101'
    assert m['level1_readiness_metadata_history_enabled'] is True
    assert m['level1_readiness_metadata_history_browser_storage_only'] is True
    assert m['level1_readiness_metadata_history_backend_mutation_enabled'] is False
    assert m['level1_readiness_metadata_history_upload_enabled'] is False
    assert m['level1_readiness_metadata_history_decides_readiness'] is False
    assert m['level1_readiness_metadata_history_computes_execution_eligibility'] is False
    assert m['level1_readiness_metadata_history_execution_enabled'] is False
    assert m['runtime_level'] == 'level_0_manual_only'
