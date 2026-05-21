from pathlib import Path

DOCS = [
    Path('docs/atlas_development_handoff.md'),
    Path('docs/atlas_scale_master_roadmap.md'),
    Path('docs/atlas_unified_autopilot_checkpoint.md'),
    Path('docs/atlas_autopilot_current_status.md'),
    Path('docs/atlas_autopilot_scale_master_plan.md'),
]


def test_active_pointer_and_next_pr_73b():
    for p in DOCS:
        t = p.read_text(encoding='utf-8')
        assert 'PR-ATLAS-SCALE-73B' in t
        assert 'Next PR:\n- PR-ATLAS-SCALE-74: Minimal Atlas Workflow UI shell' in t


def test_goal_and_scope_language_73b():
    all_text = '\n'.join(p.read_text(encoding='utf-8') for p in DOCS)
    assert 'fully autonomous code agent' in all_text
    assert 'self-improving CodeAgentPersonal / KasaneCore' in all_text or 'self-improving CodeAgentPersonal/KasaneCore' in all_text
    assert 'PR-91〜PR-100 Self-Improving Atlas / KasaneCore Roadmap' in all_text
    assert 'Execution semantics remain unchanged.' in all_text or 'no execution semantics change' in all_text
    assert 'Current next PR' not in all_text
    assert 'ThinUI is the final goal' not in all_text
