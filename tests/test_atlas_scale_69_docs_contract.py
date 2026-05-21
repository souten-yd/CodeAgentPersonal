from pathlib import Path


def test_docs_active_pointer_updated_to_scale_69_70():
    files = [
        'docs/atlas_development_handoff.md',
        'docs/atlas_unified_autopilot_checkpoint.md',
        'docs/atlas_autopilot_current_status.md',
        'docs/atlas_autopilot_scale_master_plan.md',
        'docs/atlas_scale_master_roadmap.md',
    ]
    text = '\n'.join(Path(f).read_text() for f in files)
    assert 'Current PR:\n- PR-ATLAS-SCALE-69' in text
    assert 'PR-ATLAS-SCALE-70: Operator Loop uses verification recommendation handoff metadata for manual approval summary' in text
