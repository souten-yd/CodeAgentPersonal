import json
from pathlib import Path

manifest = json.loads(Path('web/atlas_ui_surface_manifest.json').read_text())
docs = '\n'.join(
    Path(p).read_text()
    for p in [
        'docs/atlas_scale_master_roadmap.md',
        'docs/atlas_development_handoff.md',
        'docs/atlas_autonomous_execution_readiness_policy.md',
        'docs/atlas_thinui_readiness.md',
        'docs/atlas_vue_migration_plan.md',
    ]
)


def test_102b_manifest_and_docs_alignment():
    assert manifest['level1_readiness_metadata_history_import_export_checkpoint'] == 'PR-ATLAS-SCALE-102'
    assert manifest['runtime_level'] == 'level_0_manual_only'
    assert manifest['level1_execution_enabled'] is False
    assert manifest['autonomous_execution_enabled'] is False
    assert 'Current automation track: PR-ATLAS-SCALE-103' in docs
    assert 'Next automation track: PR-ATLAS-SCALE-103' in docs
    assert 'PR-ATLAS-SCALE-103 may add local-only history diff view' in docs
