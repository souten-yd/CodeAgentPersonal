import json
from pathlib import Path


def test_manifest_scale_99_export_flags_and_safety_persist():
    m = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    assert m['level1_readiness_metadata_export_checkpoint'] == 'PR-ATLAS-SCALE-99'
    assert m['level1_readiness_metadata_export_enabled'] is True
    assert m['level1_readiness_metadata_export_local_only'] is True
    assert m['level1_readiness_metadata_copy_enabled'] is True
    assert m['level1_readiness_metadata_export_backend_mutation_enabled'] is False
    assert m['level1_readiness_metadata_export_upload_enabled'] is False
    assert m['level1_readiness_metadata_export_execution_enabled'] is False
    assert m['level1_readiness_metadata_export_decides_readiness'] is False
    assert m['level1_readiness_metadata_export_computes_execution_eligibility'] is False
    assert m['runtime_level'] == 'level_0_manual_only'
    assert m['level1_execution_enabled'] is False
    assert m['autonomous_execution_enabled'] is False
