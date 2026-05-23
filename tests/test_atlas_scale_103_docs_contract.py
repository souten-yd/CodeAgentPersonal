from pathlib import Path
DOCS='\n'.join(Path(p).read_text() for p in [
'docs/atlas_scale_master_roadmap.md','docs/atlas_development_handoff.md','docs/atlas_autonomous_execution_readiness_policy.md','docs/atlas_thinui_readiness.md','docs/atlas_vue_migration_plan.md'])

def test_docs_scale_103_state_and_104_next_track():
    required=[
        'PR-ATLAS-SCALE-103 completed',
        'Completed automation PR: PR-ATLAS-SCALE-103',
        'Current automation track: PR-ATLAS-SCALE-104',
        'Next automation track: PR-ATLAS-SCALE-104',
    ]
    for token in required:
        assert token in DOCS
