import json
from pathlib import Path

MANIFEST = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text())


def test_scale_105_manifest_fields():
    expected = {
        'level1_readiness_metadata_history_diff_export_checkpoint': 'PR-ATLAS-SCALE-105',
        'level1_readiness_metadata_history_diff_export_enabled': True,
        'level1_readiness_metadata_history_diff_export_local_only': True,
        'level1_readiness_metadata_history_diff_export_upload_enabled': False,
        'level1_readiness_metadata_history_diff_export_backend_mutation_enabled': False,
        'level1_readiness_metadata_history_diff_export_decides_readiness': False,
        'level1_readiness_metadata_history_diff_export_computes_execution_eligibility': False,
        'level1_readiness_metadata_history_diff_export_execution_enabled': False,
        'level1_next_pr_may_add_history_diff_annotation_local_only': True,
        'level1_next_pr_must_not_enable_execution': True,
    }
    for k, v in expected.items():
        assert k in MANIFEST, f'missing manifest key: {k}'
        assert MANIFEST.get(k) == v


def test_scale_103_manifest_fields_preserved():
    expected = {
        'level1_readiness_metadata_history_diff_checkpoint': 'PR-ATLAS-SCALE-103',
        'level1_readiness_metadata_history_diff_enabled': True,
        'level1_readiness_metadata_history_diff_local_only': True,
        'level1_readiness_metadata_history_diff_upload_enabled': False,
        'level1_readiness_metadata_history_diff_backend_mutation_enabled': False,
        'level1_readiness_metadata_history_diff_decides_readiness': False,
        'level1_readiness_metadata_history_diff_computes_execution_eligibility': False,
        'level1_readiness_metadata_history_diff_execution_enabled': False,
        'level1_next_pr_may_add_history_diff_annotation_local_only': True,
    }
    for k, v in expected.items():
        assert MANIFEST.get(k) == v


def test_preserve_runtime_safety():
    assert MANIFEST['runtime_level'] == 'level_0_manual_only'
    assert MANIFEST['level1_execution_enabled'] is False
    assert MANIFEST['autonomous_execution_enabled'] is False
