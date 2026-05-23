import json
from pathlib import Path
MANIFEST = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text())

def test_scale_103_manifest_fields():
    expected = {
        'level1_readiness_metadata_history_diff_checkpoint': 'PR-ATLAS-SCALE-103',
        'level1_readiness_metadata_history_diff_enabled': True,
        'level1_readiness_metadata_history_diff_local_only': True,
        'level1_readiness_metadata_history_diff_upload_enabled': False,
        'level1_readiness_metadata_history_diff_backend_mutation_enabled': False,
        'level1_readiness_metadata_history_diff_decides_readiness': False,
        'level1_readiness_metadata_history_diff_computes_execution_eligibility': False,
        'level1_readiness_metadata_history_diff_execution_enabled': False,
        'level1_next_pr_may_add_history_diff_filtering_local_only': True,
        'level1_next_pr_must_not_enable_execution': True,
    }
    for k, v in expected.items():
        assert MANIFEST.get(k) == v

def test_scale_102_fields_preserved():
    assert MANIFEST['level1_readiness_metadata_history_import_export_checkpoint'] == 'PR-ATLAS-SCALE-102'
    assert MANIFEST['runtime_level'] == 'level_0_manual_only'
    assert MANIFEST['level1_execution_enabled'] is False
    assert MANIFEST['autonomous_execution_enabled'] is False


def test_scale_103_runtime_safety_flags_preserved():
    assert MANIFEST['runtime_level'] == 'level_0_manual_only'
    assert MANIFEST['level1_execution_enabled'] is False
    assert MANIFEST['autonomous_execution_enabled'] is False
