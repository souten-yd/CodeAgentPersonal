from pathlib import Path

DOCS = [
    'docs/atlas_development_handoff.md',
    'docs/atlas_scale_master_roadmap.md',
    'docs/atlas_vue_migration_plan.md',
    'docs/atlas_thinui_readiness.md',
]


def test_docs_current_track_state_updated_for_vue20_completion() -> None:
    for f in DOCS:
        text = Path(f).read_text(encoding='utf-8')
        assert 'PR-ATLAS-VUE-20 completed' in text
        assert 'Completed UI PRs: PR-ATLAS-VUE-01 through PR-ATLAS-VUE-21' in text
        assert 'Current UI track: Vue defaultization complete' in text
        assert 'Planned UI track: return to PR-ATLAS-SCALE-93 automation track' in text
        assert 'Current automation track: PR-ATLAS-SCALE-93' in text
        assert 'legacy UI remains available via /ui/' in text
        assert 'runtime remains level_0_manual_only' in text
        assert 'Vue execution capability remains none' in text
        assert 'VUE21 completed default-enable only, not execution-enable' in text
        assert 'next work returns to PR-ATLAS-SCALE-93' in text
