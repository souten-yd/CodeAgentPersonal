from pathlib import Path

def test_docs_pointers():
    s='\n'.join(Path(p).read_text() for p in ['docs/atlas_development_handoff.md','docs/atlas_unified_autopilot_checkpoint.md','docs/atlas_autopilot_current_status.md','docs/atlas_autopilot_scale_master_plan.md','docs/atlas_scale_master_roadmap.md'])
    assert 'PR-ATLAS-SCALE-67' in s
    assert 'PR-ATLAS-SCALE-68: Verification Recommendation UI using Planner Packaging v2' in s
    assert 'PlanItem Impact Map' in s and 'Context Refresh v2' in s
