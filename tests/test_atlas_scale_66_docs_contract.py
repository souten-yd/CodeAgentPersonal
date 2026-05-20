from pathlib import Path


def test_docs_pointers_updated():
    files=['docs/atlas_development_handoff.md','docs/atlas_unified_autopilot_checkpoint.md','docs/atlas_autopilot_current_status.md','docs/atlas_autopilot_scale_master_plan.md','docs/atlas_scale_master_roadmap.md']
    text='\n'.join(Path(f).read_text(encoding='utf-8') for f in files)
    assert 'PR-ATLAS-SCALE-66' in text
    assert 'PR-ATLAS-SCALE-67: Planner Packaging v2 using Context Refresh v2 and PlanItem Impact Map' in text
    assert 'Current next PR: PR-ATLAS-SCALE-65' not in text
