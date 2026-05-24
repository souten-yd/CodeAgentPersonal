import json
from pathlib import Path


def test_manifest_scale_110_label_export_local_only_fields():
    p = Path('web/atlas_ui_surface_manifest.json')
    text = p.read_text(encoding='utf-8')
    m = json.loads(text)
    assert m['level1_readiness_metadata_history_diff_label_export_checkpoint'] == 'PR-ATLAS-SCALE-110'
    assert m['level1_readiness_metadata_history_diff_label_export_enabled'] is True
    assert m['level1_readiness_metadata_history_diff_label_export_local_only'] is True
    assert m['level1_readiness_metadata_history_diff_label_export_upload_enabled'] is False
    assert m['level1_readiness_metadata_history_diff_label_export_backend_mutation_enabled'] is False
    assert m['level1_readiness_metadata_history_diff_label_export_decides_readiness'] is False
    assert m['level1_readiness_metadata_history_diff_label_export_computes_execution_eligibility'] is False
    assert m['level1_readiness_metadata_history_diff_label_export_execution_enabled'] is False
    assert m['level1_next_pr_may_add_history_diff_label_import_local_only'] is True
    assert 'level1_next_pr_may_add_history_diff_label_export_local_only' not in m
    assert m['level1_next_pr_must_not_enable_execution'] is True
    assert text.count('"level1_next_pr_must_not_enable_execution"') == 1
    assert m['runtime_level'] == 'level_0_manual_only'
    assert m['level1_execution_enabled'] is False
    assert m['autonomous_execution_enabled'] is False
