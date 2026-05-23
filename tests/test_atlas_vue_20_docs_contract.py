from pathlib import Path
DOCS = ['docs/atlas_development_handoff.md','docs/atlas_scale_master_roadmap.md','docs/atlas_vue_migration_plan.md','docs/atlas_thinui_readiness.md']

def test_docs_current_track_state_updated_for_vue20_completion() -> None:
    for f in DOCS:
        text = Path(f).read_text(encoding='utf-8')
        assert 'PR-ATLAS-VUE-20 completed' in text
        assert 'Current UI track: PR-ATLAS-VUE-21' in text
        assert 'Planned UI track: PR-ATLAS-VUE-21 only' in text
        assert 'Existing ui.html remains default until PR-ATLAS-VUE-21' in text
        assert 'VUE20 does not redirect / or /ui.html' in text
