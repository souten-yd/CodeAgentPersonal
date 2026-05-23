from pathlib import Path

DOCS = [
    'docs/atlas_development_handoff.md',
    'docs/atlas_scale_master_roadmap.md',
    'docs/atlas_vue_migration_plan.md',
    'docs/atlas_thinui_readiness.md',
]


def test_docs_track_state_for_vue19_to_vue20_transition() -> None:
    for f in DOCS:
        text = Path(f).read_text(encoding='utf-8')
        assert 'PR-ATLAS-VUE-19 completed' in text
        assert 'Completed UI PRs: PR-ATLAS-VUE-01 through PR-ATLAS-VUE-20' in text
        assert 'Current UI track: PR-ATLAS-VUE-21' in text
        assert 'Planned UI track: PR-ATLAS-VUE-21 only' in text
        assert 'Current automation track: PR-ATLAS-SCALE-93' in text
        assert 'Existing ui.html remains default until PR-ATLAS-VUE-21' in text
        assert 'runtime remains level_0_manual_only' in text
        assert 'Vue execution capability remains none' in text
        assert 'VUE21 is default-enable checkpoint, not execution-enable checkpoint.' in text
