from pathlib import Path

DOCS = [
    'docs/atlas_development_handoff.md',
    'docs/atlas_scale_master_roadmap.md',
    'docs/atlas_autonomous_execution_readiness_policy.md',
    'docs/atlas_thinui_readiness.md',
    'docs/atlas_vue_migration_plan.md',
]


def test_docs_scale_100_completion_and_101_pointer_contract():
    for d in DOCS:
        t = Path(d).read_text(encoding='utf-8')
        assert 'PR-ATLAS-SCALE-100 completed' in t
        assert 'Completed automation PR: PR-ATLAS-SCALE-101' in t
        assert 'Current automation track: PR-ATLAS-SCALE-103' in t
        assert 'Next automation track: PR-ATLAS-SCALE-103' in t
        assert 'next work is PR-ATLAS-SCALE-103' in t
        assert 'next work is PR-ATLAS-SCALE-100' not in t
        assert 'Planned UI track: return to PR-ATLAS-SCALE-100 automation track' not in t
        assert 'level_0_manual_only' in t
        assert 'Level-1 execution remains disabled' in t
        assert 'Autonomous execution remains disabled' in t
        assert 'Vue execution capability remains none' in t
        assert 'backend workflow_state remains authoritative' in t


def test_docs_scale_101_scope_is_local_metadata_history_only():
    t = Path('docs/atlas_scale_master_roadmap.md').read_text(encoding='utf-8').lower()
    assert 'browser storage' in t
    assert 'level-1 execution remains disabled' in t
