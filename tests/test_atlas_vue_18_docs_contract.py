from pathlib import Path

def test_docs_current_track_and_boundaries_updated() -> None:
    for f in ['docs/atlas_development_handoff.md','docs/atlas_scale_master_roadmap.md','docs/atlas_vue_migration_plan.md','docs/atlas_thinui_readiness.md']:
        text = Path(f).read_text(encoding='utf-8')
        assert 'PR-ATLAS-VUE-18 completed' in text
        assert 'Current UI track: Vue defaultization complete' in text
        assert 'Planned UI track: return to PR-ATLAS-SCALE-93 automation track' in text
        assert 'legacy UI remains available via /ui/' in text
        assert 'level_0_manual_only' in text
