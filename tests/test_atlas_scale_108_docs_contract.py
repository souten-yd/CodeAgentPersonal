from pathlib import Path

DOCS = [
    'docs/atlas_scale_master_roadmap.md',
    'docs/atlas_development_handoff.md',
    'docs/atlas_autonomous_execution_readiness_policy.md',
    'docs/atlas_thinui_readiness.md',
    'docs/atlas_vue_migration_plan.md',
]

def test_docs_track_progression_and_no_stale_current_state():
    for doc in DOCS:
        text = Path(doc).read_text(encoding='utf-8')
        assert 'Completed automation PR: PR-ATLAS-SCALE-108' in text
        assert 'Current automation track: PR-ATLAS-SCALE-109' in text
        assert 'Next automation track: PR-ATLAS-SCALE-109' in text
