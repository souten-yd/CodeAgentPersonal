import json
from pathlib import Path

MANIFEST = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text())


def test_manifest_scale_102_import_export_fields_exist_and_values():
    expected = {
        'level1_readiness_metadata_history_import_export_checkpoint': 'PR-ATLAS-SCALE-102',
        'level1_readiness_metadata_history_import_export_enabled': True,
        'level1_readiness_metadata_history_import_export_local_only': True,
        'level1_readiness_metadata_history_import_export_upload_enabled': False,
        'level1_readiness_metadata_history_import_export_backend_mutation_enabled': False,
        'level1_readiness_metadata_history_import_export_decides_readiness': False,
        'level1_readiness_metadata_history_import_export_computes_execution_eligibility': False,
        'level1_readiness_metadata_history_import_export_execution_enabled': False,
        'level1_next_pr_may_add_history_diff_view_local_only': True,
        'level1_next_pr_must_not_enable_execution': True,
    }
    for key, value in expected.items():
        assert key in MANIFEST
        assert MANIFEST[key] == value


def test_manifest_preserved_safety_flags():
    assert MANIFEST['level1_readiness_metadata_history_checkpoint'] == 'PR-ATLAS-SCALE-101'
    assert MANIFEST['level1_readiness_metadata_history_browser_storage_only'] is True
    assert MANIFEST['level1_readiness_metadata_history_upload_enabled'] is False
    assert MANIFEST['level1_readiness_metadata_comparison_local_only'] is True
    assert MANIFEST['level1_readiness_metadata_comparison_upload_enabled'] is False
    assert MANIFEST['level1_execution_enabled'] is False
    assert MANIFEST['runtime_level'] == 'level_0_manual_only'
    assert MANIFEST['autonomous_execution_enabled'] is False
