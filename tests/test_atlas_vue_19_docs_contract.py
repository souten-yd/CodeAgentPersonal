from pathlib import Path

def test_docs_track_state_for_vue19_to_vue20_transition() -> None:
    for f in ['docs/atlas_development_handoff.md','docs/atlas_scale_master_roadmap.md','docs/atlas_vue_migration_plan.md','docs/atlas_thinui_readiness.md']:
        text = Path(f).read_text(encoding='utf-8')
        assert 'PR-ATLAS-VUE-19 completed' in text
        assert 'Current UI track: PR-ATLAS-VUE-20' in text
        assert 'Planned UI track: PR-ATLAS-VUE-20 through PR-ATLAS-VUE-21' in text
        assert 'Existing ui.html remains default until PR-ATLAS-VUE-21' in text
        assert 'VUE21 is default-enable checkpoint, not execution-enable checkpoint.' in text
