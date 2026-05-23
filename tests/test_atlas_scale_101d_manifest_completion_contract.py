import json
from pathlib import Path


def test_manifest_scale_101d_history_completion_fields_present_and_safe():
    manifest = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))

    assert manifest['level1_readiness_metadata_history_checkpoint'] == 'PR-ATLAS-SCALE-101'
    assert manifest['level1_readiness_metadata_history_enabled'] is True
    assert manifest['level1_readiness_metadata_history_browser_storage_only'] is True
    assert manifest['level1_readiness_metadata_history_backend_mutation_enabled'] is False
    assert manifest['level1_readiness_metadata_history_upload_enabled'] is False
    assert manifest['level1_readiness_metadata_history_decides_readiness'] is False
    assert manifest['level1_readiness_metadata_history_computes_execution_eligibility'] is False
    assert manifest['level1_readiness_metadata_history_execution_enabled'] is False

    assert manifest['level1_next_pr_may_add_history_import_export_local_only'] is True
    assert manifest['level1_next_pr_must_not_enable_execution'] is True

    assert manifest['runtime_level'] == 'level_0_manual_only'
    assert manifest['level1_execution_enabled'] is False
    assert manifest['autonomous_execution_enabled'] is False
