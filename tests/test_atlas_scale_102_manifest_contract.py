import json
from pathlib import Path
j=json.loads(Path('web/atlas_ui_surface_manifest.json').read_text())

def test_manifest_scale_102_fields():
    assert j['level1_readiness_metadata_history_import_export_checkpoint']=='PR-ATLAS-SCALE-102'
    assert j['level1_readiness_metadata_history_import_export_local_only'] is True
    assert j['level1_readiness_metadata_history_import_export_upload_enabled'] is False
    assert j['runtime_level']=='level_0_manual_only'
