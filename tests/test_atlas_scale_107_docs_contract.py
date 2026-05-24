from pathlib import Path
DOCS='\n'.join(Path(p).read_text() for p in ['docs/atlas_scale_master_roadmap.md','docs/atlas_development_handoff.md','docs/atlas_autonomous_execution_readiness_policy.md','docs/atlas_thinui_readiness.md','docs/atlas_vue_migration_plan.md'])
def test_scale_107_108_pointers_present():
    for t in ['PR-ATLAS-SCALE-107 completed','Completed automation PR: PR-ATLAS-SCALE-107','Current automation track: PR-ATLAS-SCALE-108','Next automation track: PR-ATLAS-SCALE-108','next work is PR-ATLAS-SCALE-108']:
        assert t in DOCS
