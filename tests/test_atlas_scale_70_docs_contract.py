from pathlib import Path
DOCS=['docs/atlas_development_handoff.md','docs/atlas_unified_autopilot_checkpoint.md','docs/atlas_autopilot_current_status.md','docs/atlas_autopilot_scale_master_plan.md','docs/atlas_scale_master_roadmap.md']
def _active(doc):
    return Path(doc).read_text(encoding='utf-8').split('\n# ',1)[0]
def test_active_sections_point_to_70_and_71_not_68_69():
    for d in DOCS:
        a=_active(d)
        assert 'PR-ATLAS-SCALE-70' in a and 'PR-ATLAS-SCALE-71' in a
        assert 'Current PR:\n- PR-ATLAS-SCALE-69' not in a
        assert 'manual approval summary' in a and 'advisory-only' in a and 'EXECUTE ONE ACTION' in a
