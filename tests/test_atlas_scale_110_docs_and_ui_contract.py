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
