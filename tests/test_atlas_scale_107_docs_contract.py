from pathlib import Path

DOC_PATHS = [
    'docs/atlas_scale_master_roadmap.md',
    'docs/atlas_development_handoff.md',
    'docs/atlas_autonomous_execution_readiness_policy.md',
    'docs/atlas_thinui_readiness.md',
    'docs/atlas_vue_migration_plan.md',
]


def _read(path: str) -> str:
    return Path(path).read_text(encoding='utf-8')


def _section(text: str, heading: str) -> str:
    marker = f'## {heading}'
    start = text.find(marker)
    assert start != -1, f'missing section: {heading}'
    start += len(marker)
    rest = text[start:]
    next_idx = rest.find('\n## ')
    return rest[:next_idx] if next_idx != -1 else rest


def test_active_pr_pointer_and_current_track_sections_are_scale_109_chain():
    for path in DOC_PATHS:
        text = _read(path)

        current_state = _section(text, 'Current Atlas Vue UI Track State')
        assert 'Planned UI track: return to PR-ATLAS-SCALE-110 automation track' in current_state
        assert 'Current automation track: PR-ATLAS-SCALE-110' in current_state
        assert 'Next automation track: PR-ATLAS-SCALE-110' in current_state
        assert 'next work is PR-ATLAS-SCALE-110' in current_state

        assert 'Planned UI track: return to PR-ATLAS-SCALE-107 automation track' not in current_state
        assert 'Current automation track: PR-ATLAS-SCALE-107' not in current_state
        assert 'Next automation track: PR-ATLAS-SCALE-107' not in current_state
        assert 'next work is PR-ATLAS-SCALE-107' not in current_state

        if '## Active PR Pointer (Updated)' in text:
            active = _section(text, 'Active PR Pointer (Updated)')
        elif '## Current Execution Boundary' in text:
            active = _section(text, 'Current Execution Boundary')
        else:
            continue

        assert 'Completed automation PR: PR-ATLAS-SCALE-109' in active
        assert 'Current automation track: PR-ATLAS-SCALE-110' in active
        assert 'Next automation track: PR-ATLAS-SCALE-110' in active


def test_scale_107_completion_and_safety_statements_remain_present():
    docs = '\n'.join(_read(path) for path in DOC_PATHS)
    required_tokens = [
        'PR-ATLAS-SCALE-107 completed',
        'local-only readiness metadata history diff bookmarks',
        'browser-local/display-only',
        'no metadata upload',
        'no backend mutation',
        'no readiness decision',
        'no execution eligibility computation',
        'no execution controls',
        'runtime remains level_0_manual_only',
        'Level-1/autonomous execution remain disabled',
        'backend workflow_state remains authoritative',
        'Vue execution capability remains none',
        'next PR may add local-only diff label export, not execution enable',
        'desktop submenu/right-pane layout regression contract',
    ]
    for token in required_tokens:
        assert token in docs
