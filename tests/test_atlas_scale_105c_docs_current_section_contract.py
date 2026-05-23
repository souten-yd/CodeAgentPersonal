from pathlib import Path

DOC_PATHS = [
    'docs/atlas_scale_master_roadmap.md',
    'docs/atlas_development_handoff.md',
    'docs/atlas_autonomous_execution_readiness_policy.md',
    'docs/atlas_thinui_readiness.md',
    'docs/atlas_vue_migration_plan.md',
]

REQUIRED_SCALE_105_SUMMARY_TOKENS = [
    'local-only readiness metadata history diff export/copy',
    'browser-local/display-only',
    'no metadata upload',
    'no backend mutation',
    'no readiness decision',
    'no execution eligibility computation',
    'no execution controls',
    'runtime remains level_0_manual_only',
    'Level-1/autonomous execution remain disabled',
    'backend workflow_state remains authoritative',
]


def _section_slice(text: str, heading: str) -> str:
    marker = f'## {heading}'
    if marker not in text:
        return ''
    after = text.split(marker, 1)[1]
    if '\n## ' in after:
        after = after.split('\n## ', 1)[0]
    return after


def test_active_pr_pointer_uses_canonical_scale_106_track_tokens():
    for path in DOC_PATHS:
        text = Path(path).read_text()
        section = _section_slice(text, 'Active PR Pointer (Updated)')
        if not section:
            continue
        assert 'Completed automation PR: PR-ATLAS-SCALE-105' in section
        assert 'Current automation track: PR-ATLAS-SCALE-106' in section
        assert 'Next automation track: PR-ATLAS-SCALE-106' in section


def test_current_vue_ui_track_state_uses_canonical_scale_106_tokens_and_forbids_stale_105_markers():
    stale = [
        'Planned UI track: return to PR-ATLAS-SCALE-105 automation track',
        'Current automation track: PR-ATLAS-SCALE-105',
        'Next automation track: PR-ATLAS-SCALE-105',
        'next work is PR-ATLAS-SCALE-105',
    ]
    for path in DOC_PATHS:
        text = Path(path).read_text()
        section = _section_slice(text, 'Current Atlas Vue UI Track State')
        if not section:
            continue
        assert 'Planned UI track: return to PR-ATLAS-SCALE-106 automation track' in section
        assert 'Current automation track: PR-ATLAS-SCALE-106' in section
        assert 'Next automation track: PR-ATLAS-SCALE-106' in section
        assert 'next work is PR-ATLAS-SCALE-106' in section
        for token in stale:
            assert token not in section, f'stale token remained in current-state section: {path} :: {token}'


def test_scale_105_completed_summary_safety_contract_remains_present():
    docs = '\n'.join(Path(path).read_text() for path in DOC_PATHS)
    for token in REQUIRED_SCALE_105_SUMMARY_TOKENS:
        assert token in docs
