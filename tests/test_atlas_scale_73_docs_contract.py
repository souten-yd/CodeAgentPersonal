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
        assert 'Completed:\n- PR-ATLAS-SCALE-73' in t
        assert 'Current PR:\n- PR-ATLAS-SCALE-73' in t
        assert 'Next PR:\n- PR-ATLAS-SCALE-74: Minimal Atlas Workflow UI shell' in t


def test_no_stale_current_next_pr_phrase_in_restart_or_history():
    for p in DOCS:
        t = p.read_text(encoding='utf-8')
        assert 'Current next PR' not in t
        assert 'Next implementation PR: PR-ATLAS-SCALE-70' not in t


def test_scale_73_doc_goals_and_roadmap_language():
    t = Path('docs/atlas_scale_master_roadmap.md').read_text(encoding='utf-8')
    assert 'ThinUI' in t
    assert 'Minimal Atlas Workflow UI shell' in t
    assert 'fully autonomous code agent' in t
    assert 'no execution semantics change' in t
    assert 'PR-81〜PR-90 Autonomous Code Agent Execution Roadmap' in t or 'PR-81+ Autonomous' in t
