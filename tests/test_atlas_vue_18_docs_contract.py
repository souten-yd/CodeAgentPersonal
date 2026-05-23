from pathlib import Path

def test_docs_current_track_and_boundaries_updated() -> None:
    for f in ['docs/atlas_development_handoff.md','docs/atlas_scale_master_roadmap.md','docs/atlas_vue_migration_plan.md','docs/atlas_thinui_readiness.md']:
        text = Path(f).read_text(encoding='utf-8')
        assert 'PR-ATLAS-VUE-18 completed' in text
        assert 'Current UI track: PR-ATLAS-VUE-19' in text
        assert 'Planned UI track: PR-ATLAS-VUE-19 through PR-ATLAS-VUE-21' in text
        assert 'Existing ui.html remains default until PR-ATLAS-VUE-21' in text
        assert 'level_0_manual_only' in text
