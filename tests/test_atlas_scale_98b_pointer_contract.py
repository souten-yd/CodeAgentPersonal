from pathlib import Path

DOCS = [
    'docs/atlas_scale_master_roadmap.md',
    'docs/atlas_development_handoff.md',
    'docs/atlas_autonomous_execution_readiness_policy.md',
    'docs/atlas_thinui_readiness.md',
    'docs/atlas_vue_migration_plan.md',
]


def test_scale_98b_pointer_contract() -> None:
    for d in DOCS:
        text = Path(d).read_text(encoding='utf-8')
        assert 'PR-ATLAS-SCALE-98 completed' in text
        assert 'Completed automation PR: PR-ATLAS-SCALE-98' in text
        assert 'Current automation track: PR-ATLAS-SCALE-99' in text
        assert 'Next automation track: PR-ATLAS-SCALE-99' in text
        assert 'next work is PR-ATLAS-SCALE-99' in text
        assert 'next work is PR-ATLAS-SCALE-98' not in text
        assert 'Planned UI track: return to PR-ATLAS-SCALE-98 automation track' not in text
