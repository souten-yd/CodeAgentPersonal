from pathlib import Path

DOC_PATHS = [
    'docs/atlas_scale_master_roadmap.md',
    'docs/atlas_development_handoff.md',
    'docs/atlas_autonomous_execution_readiness_policy.md',
    'docs/atlas_thinui_readiness.md',
    'docs/atlas_vue_migration_plan.md',
]
DOCS = '\n'.join(Path(p).read_text() for p in DOC_PATHS)


def test_docs_advance_to_scale_104_complete_105_current_next():
    for token in [
        'PR-ATLAS-SCALE-104 completed.',
        'Completed automation PR: PR-ATLAS-SCALE-104',
        'Current automation track: PR-ATLAS-SCALE-107',
        'Next automation track: PR-ATLAS-SCALE-107',
        'next work is PR-ATLAS-SCALE-107',
        'Next PR may add local-only diff export and must not enable execution.',
        'backend workflow_state remains authoritative',
    ]:
        assert token in DOCS


def test_current_state_sections_forbid_stale_scale_104_pointers_and_duplicates():
    for path in DOC_PATHS:
        text = Path(path).read_text()
        current_slice = text[:2200]
        assert 'Current automation track: PR-ATLAS-SCALE-104' not in current_slice
        assert 'Next automation track: PR-ATLAS-SCALE-104' not in current_slice
        assert 'next work is PR-ATLAS-SCALE-104' not in current_slice
        assert 'Planned UI track: return to PR-ATLAS-SCALE-104 automation track' not in current_slice
        assert current_slice.count('Current automation track: PR-ATLAS-SCALE-107') <= 1
