from pathlib import Path
DOC_PATHS=['docs/atlas_scale_master_roadmap.md','docs/atlas_development_handoff.md','docs/atlas_autonomous_execution_readiness_policy.md','docs/atlas_thinui_readiness.md','docs/atlas_vue_migration_plan.md']
DOCS='\n'.join(Path(p).read_text() for p in DOC_PATHS)

def test_docs_advance_to_scale_105_complete_106_current_next():
    for token in ['PR-ATLAS-SCALE-105 completed','Completed automation PR: PR-ATLAS-SCALE-105','Current automation track: PR-ATLAS-SCALE-106','Next automation track: PR-ATLAS-SCALE-106','next work is PR-ATLAS-SCALE-106','local-only readiness metadata history diff export/copy','backend workflow_state remains authoritative']:
        assert token in DOCS
