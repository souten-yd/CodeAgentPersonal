import json
from pathlib import Path


def test_vue_12_manifest_packaging_metadata_and_preserved_fields() -> None:
    m = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text(encoding='utf-8'))
    assert m['vue_next_packaging_readiness_checkpoint'] == 'PR-ATLAS-VUE-12'
    assert m['vue_next_packaging_policy_defined'] is True
    assert m['vue_next_deployment_readiness_defined'] is True
    assert m['vue_next_dist_packaging_policy'] == 'dist_required_validated'
    assert m['vue_next_dist_source_of_truth'] is False
    assert m['vue_next_source_dir'] == 'web/atlas-next'
    assert m['vue_next_dist_dir'] == 'web/atlas-next/dist'
    assert m['vue_next_preview_health'] == 'observable_fail_closed'
    assert m['vue_next_preview_diagnostics_endpoint'] == '/api/atlas/vue-next-preview/diagnostics'
    assert m['vue_next_default_enabled'] is False
    assert m['vue_next_execution_enabled'] is False
    assert m['runtime_level'] == 'level_0_manual_only'
