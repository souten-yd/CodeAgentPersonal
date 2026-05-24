import json
from pathlib import Path


def test_manifest_scale_109_fields_and_runtime_safety():
    m = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    assert m['level1_readiness_metadata_history_diff_label_filter_checkpoint'] == 'PR-ATLAS-SCALE-109'
    assert m['level1_readiness_metadata_history_diff_label_filter_enabled'] is True
    assert m['level1_readiness_metadata_history_diff_label_filter_local_only'] is True
    assert m['level1_readiness_metadata_history_diff_label_filter_upload_enabled'] is False
    assert m['level1_readiness_metadata_history_diff_label_filter_backend_mutation_enabled'] is False
    assert m['level1_readiness_metadata_history_diff_label_filter_decides_readiness'] is False
    assert m['level1_readiness_metadata_history_diff_label_filter_computes_execution_eligibility'] is False
    assert m['level1_readiness_metadata_history_diff_label_filter_execution_enabled'] is False
    assert m['runtime_level'] == 'level_0_manual_only'
    assert m['level1_execution_enabled'] is False
    assert m['autonomous_execution_enabled'] is False
