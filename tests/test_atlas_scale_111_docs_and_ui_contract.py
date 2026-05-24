from pathlib import Path

DOCS = [
    'docs/atlas_scale_master_roadmap.md',
    'docs/atlas_development_handoff.md',
    'docs/atlas_autonomous_execution_readiness_policy.md',
    'docs/atlas_thinui_readiness.md',
    'docs/atlas_vue_migration_plan.md',
]

def test_docs_advance_to_scale_112_pointer_after_scale_111():
    for doc in DOCS:
        text = Path(doc).read_text(encoding='utf-8')
        assert 'Completed automation PR: PR-ATLAS-SCALE-111' in text
        assert 'Current automation track: PR-ATLAS-SCALE-112' in text
        assert 'Next automation track: PR-ATLAS-SCALE-112' in text
        assert 'Planned UI track: return to PR-ATLAS-SCALE-112 automation track' in text
        assert 'next work is PR-ATLAS-SCALE-112' in text
        assert 'next PR may add local-only diff label conflict resolution, not execution enable' in text


def test_scale_111_label_import_ui_and_local_only_safety_contract():
    text = Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text(encoding='utf-8')
    required = [
        'Merge imported labels', 'Replace local labels', 'local_diff_labels', 'local_diff_label_filtered_items',
        'parseImportedDiffLabels', "importDiffLabelsFromText(mode: 'merge' | 'replace')", 'JSON.parse', 'FileReader',
        'Imported', 'invalid JSON', 'never uploaded and never mutate backend'
    ]
    for token in required:
        assert token in text
    for forbidden in ['/api/level1/execute', '/api/level1/dry-run', '/api/level1/approval', '/api/level1/apply', '/api/level1/verify', '/api/level1/rollback', '/api/level1/retry', '/api/level1/continue', 'fetch(']:
        assert forbidden not in text
