from pathlib import Path

DOCS = [
    Path('docs/atlas_development_handoff.md'),
    Path('docs/atlas_scale_master_roadmap.md'),
    Path('docs/atlas_unified_autopilot_checkpoint.md'),
    Path('docs/atlas_autopilot_current_status.md'),
    Path('docs/atlas_autopilot_scale_master_plan.md'),
]


def test_active_pointer_and_next_pr():
    for p in DOCS:
        t = p.read_text(encoding='utf-8')
        assert 'Completed:\n- PR-ATLAS-SCALE-73B' in t
        assert 'Current PR:\n- PR-ATLAS-SCALE-73B' in t
        assert 'Next PR:\n- PR-ATLAS-SCALE-74: Minimal Atlas Workflow UI shell' in t
