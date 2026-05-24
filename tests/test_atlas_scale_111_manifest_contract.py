import json
from pathlib import Path


def test_manifest_scale_111_label_import_local_only_fields():
    p = Path('web/atlas_ui_surface_manifest.json')
    text = p.read_text(encoding='utf-8')
    m = json.loads(text)
    assert m['level1_readiness_metadata_history_diff_label_import_checkpoint'] == 'PR-ATLAS-SCALE-111'
    assert m['level1_readiness_metadata_history_diff_label_import_enabled'] is True
    assert m['level1_readiness_metadata_history_diff_label_import_local_only'] is True
    assert m['level1_readiness_metadata_history_diff_label_import_upload_enabled'] is False
    assert m['level1_readiness_metadata_history_diff_label_import_backend_mutation_enabled'] is False
    assert m['level1_readiness_metadata_history_diff_label_import_decides_readiness'] is False
    assert m['level1_readiness_metadata_history_diff_label_import_computes_execution_eligibility'] is False
    assert m['level1_readiness_metadata_history_diff_label_import_execution_enabled'] is False
    assert m['level1_next_pr_may_add_history_diff_label_conflict_resolution_local_only'] is True
    assert m['level1_next_pr_must_not_enable_execution'] is True
    assert text.count('"level1_next_pr_must_not_enable_execution"') == 1
