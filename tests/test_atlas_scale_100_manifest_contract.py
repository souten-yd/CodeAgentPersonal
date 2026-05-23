import json
from pathlib import Path


def test_manifest_has_scale_100_comparison_flags():
    m = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    assert m['level1_readiness_metadata_comparison_checkpoint'] == 'PR-ATLAS-SCALE-100'
    assert m['level1_readiness_metadata_comparison_enabled'] is True
    assert m['level1_readiness_metadata_comparison_local_only'] is True
    assert m['level1_readiness_metadata_comparison_upload_enabled'] is False
    assert m['level1_readiness_metadata_comparison_backend_mutation_enabled'] is False
    assert m['level1_readiness_metadata_comparison_decides_readiness'] is False
    assert m['level1_readiness_metadata_comparison_computes_execution_eligibility'] is False
    assert m['level1_readiness_metadata_comparison_execution_enabled'] is False
    assert m['level1_next_pr_may_add_metadata_history_local_storage'] is True
    assert m['level1_next_pr_must_not_enable_execution'] is True
    assert m['runtime_level'] == 'level_0_manual_only'
