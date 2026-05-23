from pathlib import Path
DOCS='\n'.join(Path(p).read_text() for p in ['docs/atlas_scale_master_roadmap.md','docs/atlas_development_handoff.md','docs/atlas_autonomous_execution_readiness_policy.md','docs/atlas_thinui_readiness.md','docs/atlas_vue_migration_plan.md'])

def test_docs_advance_to_scale_104_complete_105_current_next():
    for token in ['PR-ATLAS-SCALE-104 completed.','Completed automation PR: PR-ATLAS-SCALE-104','Current automation track: PR-ATLAS-SCALE-105','Next automation track: PR-ATLAS-SCALE-105','next work is PR-ATLAS-SCALE-105','Next PR may add local-only diff export and must not enable execution.']:
        assert token in DOCS
