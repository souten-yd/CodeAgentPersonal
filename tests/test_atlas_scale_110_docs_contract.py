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


def test_docs_canonical_scale_110b_pointers_and_wording():
    for doc in DOCS:
        text = Path(doc).read_text(encoding='utf-8')
        active = _section_required(text, 'Active PR Pointer (Updated)')
        current = _section_required(text, 'Current Atlas Vue UI Track State')

        assert active.count('Completed automation PR: PR-ATLAS-SCALE-110') == 1
        assert active.count('Current automation track: PR-ATLAS-SCALE-111') == 1
        assert active.count('Next automation track: PR-ATLAS-SCALE-111') == 1
        assert 'Completed automation PR: PR-ATLAS-SCALE-109' not in active
        assert 'Current automation track: PR-ATLAS-SCALE-110' not in active
        assert 'Next automation track: PR-ATLAS-SCALE-110' not in active

        assert current.count('Planned UI track: return to PR-ATLAS-SCALE-111 automation track') == 1
        assert current.count('Current automation track: PR-ATLAS-SCALE-111') == 1
        assert current.count('Next automation track: PR-ATLAS-SCALE-111') == 1
        assert current.count('next work is PR-ATLAS-SCALE-111') == 1
        assert 'Planned UI track: return to PR-ATLAS-SCALE-110 automation track' not in current
        assert 'Current automation track: PR-ATLAS-SCALE-110' not in current
        assert 'Next automation track: PR-ATLAS-SCALE-110' not in current
        assert 'next work is PR-ATLAS-SCALE-110' not in current

        assert 'next PR may add local-only diff label export, not execution enable' not in text
        assert 'next PR may add local-only diff label import, not execution enable' in text
