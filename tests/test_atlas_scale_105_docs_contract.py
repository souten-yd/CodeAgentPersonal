from pathlib import Path

DOC_PATHS=[
    'docs/atlas_scale_master_roadmap.md',
    'docs/atlas_development_handoff.md',
    'docs/atlas_autonomous_execution_readiness_policy.md',
    'docs/atlas_thinui_readiness.md',
    'docs/atlas_vue_migration_plan.md',
]
DOCS='\n'.join(Path(p).read_text() for p in DOC_PATHS)


def _active_pointer_slice(text: str) -> str:
    marker = '## Active PR Pointer (Updated)'
    if marker not in text:
        return text
    after = text.split(marker, 1)[1]
    if '\n## ' in after:
        after = after.split('\n## ', 1)[0]
    return after


def test_docs_advance_to_scale_105_complete_106_current_next():
    required = [
        'PR-ATLAS-SCALE-106 completed',
        'Completed automation PR: PR-ATLAS-SCALE-111',
        'Current automation track: PR-ATLAS-SCALE-112',
        'Next automation track: PR-ATLAS-SCALE-112',
        'next work is PR-ATLAS-SCALE-112',
        'Planned UI track: return to PR-ATLAS-SCALE-112 automation track',
        'local-only readiness metadata history diff annotations',
        'backend workflow_state remains authoritative',
    ]
    for token in required:
        assert token in DOCS


def test_docs_current_state_slice_forbids_stale_scale_105_pointer_tokens():
    stale = [
        'Current automation track: PR-ATLAS-SCALE-105',
        'Next automation track: PR-ATLAS-SCALE-105',
        'next work is PR-ATLAS-SCALE-105',
        'Planned UI track: return to PR-ATLAS-SCALE-105 automation track',
    ]
    for path in DOC_PATHS:
        text = Path(path).read_text()
        active = _active_pointer_slice(text)
        if not active:
            continue
        for token in stale:
            assert f'- {token}' not in active, f"stale active-pointer token in {path}: {token}"


def test_active_pointer_summary_describes_scale_105_not_scale_104():
    roadmap = Path('docs/atlas_scale_master_roadmap.md').read_text()
    active = _active_pointer_slice(roadmap)
    assert 'Completed automation PR: PR-ATLAS-SCALE-111' in active
    assert 'PR-ATLAS-SCALE-106 completed: local-only readiness metadata history diff annotations' in active
    assert 'PR-ATLAS-SCALE-111 completed: local-only readiness metadata history diff filtering/grouping' not in active
