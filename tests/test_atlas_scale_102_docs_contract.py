from pathlib import Path
DOCS='\n'.join(Path(p).read_text() for p in [
'docs/atlas_scale_master_roadmap.md','docs/atlas_development_handoff.md','docs/atlas_autonomous_execution_readiness_policy.md','docs/atlas_thinui_readiness.md','docs/atlas_vue_migration_plan.md'])

def test_docs_track_advanced():
    assert 'Completed automation PR: PR-ATLAS-SCALE-102' in DOCS
    assert 'Current automation track: PR-ATLAS-SCALE-103' in DOCS
    assert 'Next automation track: PR-ATLAS-SCALE-103' in DOCS
