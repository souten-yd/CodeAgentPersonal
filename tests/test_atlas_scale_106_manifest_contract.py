import json
from pathlib import Path

MANIFEST = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text())


def test_scale_106_manifest_fields():
    expected = {
        'level1_readiness_metadata_history_diff_annotation_checkpoint': 'PR-ATLAS-SCALE-106',
        'level1_readiness_metadata_history_diff_annotation_enabled': True,
        'level1_readiness_metadata_history_diff_annotation_local_only': True,
        'level1_readiness_metadata_history_diff_annotation_upload_enabled': False,
        'level1_readiness_metadata_history_diff_annotation_backend_mutation_enabled': False,
        'level1_readiness_metadata_history_diff_annotation_decides_readiness': False,
        'level1_readiness_metadata_history_diff_annotation_computes_execution_eligibility': False,
        'level1_readiness_metadata_history_diff_annotation_execution_enabled': False,
        'level1_next_pr_may_add_history_diff_bookmarks_local_only': True,
        'level1_next_pr_must_not_enable_execution': True,
    }
    for k, v in expected.items():
        assert k in MANIFEST, f'missing manifest key: {k}'
        assert MANIFEST.get(k) == v


def test_scale_105_filtering_fields_preserved():
    expected = {
        'level1_readiness_metadata_history_diff_filtering_checkpoint': 'PR-ATLAS-SCALE-104',
        'level1_readiness_metadata_history_diff_filtering_enabled': True,
        'level1_readiness_metadata_history_diff_filtering_local_only': True,
        'level1_readiness_metadata_history_diff_filtering_upload_enabled': False,
        'level1_readiness_metadata_history_diff_filtering_backend_mutation_enabled': False,
        'level1_readiness_metadata_history_diff_filtering_decides_readiness': False,
        'level1_readiness_metadata_history_diff_filtering_computes_execution_eligibility': False,
        'level1_readiness_metadata_history_diff_filtering_execution_enabled': False,
        'level1_next_pr_may_add_history_diff_filtering_local_only': True,
    }
    for k, v in expected.items():
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
