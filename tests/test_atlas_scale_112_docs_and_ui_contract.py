from pathlib import Path

DOCS = [
    'docs/atlas_scale_master_roadmap.md',
    'docs/atlas_development_handoff.md',
    'docs/atlas_autonomous_execution_readiness_policy.md',
    'docs/atlas_thinui_readiness.md',
    'docs/atlas_vue_migration_plan.md',
]

def test_docs_advance_to_scale_113_pointer_after_scale_112():
    for doc in DOCS:
        text = Path(doc).read_text(encoding='utf-8')
        assert 'Completed automation PR: PR-ATLAS-SCALE-112' in text
        assert 'Current automation track: PR-ATLAS-SCALE-113' in text
        assert 'Next automation track: PR-ATLAS-SCALE-113' in text
        assert 'Planned UI track: return to PR-ATLAS-SCALE-113 automation track' in text
        assert 'next work is PR-ATLAS-SCALE-113' in text
        assert 'next PR may add local-only diff label conflict export, not execution enable' in text


def test_scale_112_label_conflict_resolution_ui_and_local_only_safety_contract():
    text = Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text(encoding='utf-8')
    required = [
        'previewImportedDiffLabels',
        "applyImportedLabelConflicts(mode: 'keep-existing' | 'use-imported' | 'clear-conflicts')",
        'clearLabelConflictPreview',
        'local label conflict preview',
        'Keep existing labels',
        'Use imported labels',
        'Clear conflicting labels',
        'pendingLabelImport',
        'importedLabelConflicts',
        'labelConflictStatus',
        'JSON.parse',
        'FileReader',
    ]
    for token in required:
        assert token in text
    forbidden = [
        '/api/level1/execute', '/api/level1/dry-run', '/api/level1/approval', '/api/level1/apply',
        '/api/level1/verify', '/api/level1/rollback', '/api/level1/retry', '/api/level1/continue',
        'fetch(',
    ]
    for token in forbidden:
        assert token not in text
