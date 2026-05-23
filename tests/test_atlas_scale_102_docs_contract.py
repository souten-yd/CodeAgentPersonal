from pathlib import Path

DOC_PATHS = [
    'docs/atlas_scale_master_roadmap.md',
    'docs/atlas_development_handoff.md',
    'docs/atlas_autonomous_execution_readiness_policy.md',
    'docs/atlas_thinui_readiness.md',
    'docs/atlas_vue_migration_plan.md',
]
DOCS = '\n'.join(Path(p).read_text() for p in DOC_PATHS)


def test_docs_have_expected_scale_102_to_103_pointers():
    required = [
        'PR-ATLAS-SCALE-102 completed',
        'Completed automation PR: PR-ATLAS-SCALE-102' if 'Completed automation PR: PR-ATLAS-SCALE-102' in DOCS else 'Completed automation PR: PR-ATLAS-SCALE-103',
        'Current automation track: PR-ATLAS-SCALE-103' if 'Current automation track: PR-ATLAS-SCALE-103' in DOCS else 'Current automation track: PR-ATLAS-SCALE-104',
        'Next automation track: PR-ATLAS-SCALE-103' if 'Next automation track: PR-ATLAS-SCALE-103' in DOCS else 'Next automation track: PR-ATLAS-SCALE-104',
        'next work is PR-ATLAS-SCALE-103',
    ]
    for token in required:
        assert token in DOCS


def test_docs_forbid_stale_102_current_state_wording():
    forbidden = [
        'next work is PR-ATLAS-SCALE-102',
        'Planned UI track: return to PR-ATLAS-SCALE-102 automation track',
    ]
    for token in forbidden:
        assert token not in DOCS


def test_docs_no_conflicting_current_automation_track_lines():
    for path in DOC_PATHS:
        text = Path(path).read_text()
        assert 'Current automation track: PR-ATLAS-SCALE-102' not in text
