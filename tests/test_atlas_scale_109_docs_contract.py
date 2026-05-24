from pathlib import Path

DOCS = [
    'docs/atlas_scale_master_roadmap.md',
    'docs/atlas_development_handoff.md',
    'docs/atlas_autonomous_execution_readiness_policy.md',
    'docs/atlas_thinui_readiness.md',
    'docs/atlas_vue_migration_plan.md',
]


def _section_required(text: str, heading: str) -> str:
    marker = f'## {heading}'
    assert marker in text
    tail = text.split(marker, 1)[1]
    i = tail.find('\n## ')
    return tail[:i] if i != -1 else tail


def test_docs_track_stays_canonical_post_scale_110():
    for doc in DOCS:
        text = Path(doc).read_text(encoding='utf-8')
        assert 'Completed automation PR: PR-ATLAS-SCALE-110' in text
        assert 'Current automation track: PR-ATLAS-SCALE-111' in text
        assert 'Next automation track: PR-ATLAS-SCALE-111' in text
        assert 'Planned UI track: return to PR-ATLAS-SCALE-111 automation track' in text
        assert 'next work is PR-ATLAS-SCALE-111' in text
        assert 'next PR may add local-only diff label import, not execution enable' in text
        assert 'next PR may add local-only diff label export, not execution enable' not in text


def test_roadmap_current_sections_are_strictly_scale_111_only():
    text = Path('docs/atlas_scale_master_roadmap.md').read_text(encoding='utf-8')
    active = _section_required(text, 'Active PR Pointer (Updated)')
    current = _section_required(text, 'Current Atlas Vue UI Track State')
    assert 'Current automation track: PR-ATLAS-SCALE-111' in active
    assert 'Next automation track: PR-ATLAS-SCALE-111' in active
    assert 'Current automation track: PR-ATLAS-SCALE-110' not in active
    assert 'Next automation track: PR-ATLAS-SCALE-110' not in active
    assert 'Current automation track: PR-ATLAS-SCALE-111' in current
    assert 'Next automation track: PR-ATLAS-SCALE-111' in current
    assert 'Current automation track: PR-ATLAS-SCALE-110' not in current
    assert 'Next automation track: PR-ATLAS-SCALE-110' not in current
