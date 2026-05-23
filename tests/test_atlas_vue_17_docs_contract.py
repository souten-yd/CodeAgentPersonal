from pathlib import Path

DOCS = [
    'docs/atlas_development_handoff.md',
    'docs/atlas_scale_master_roadmap.md',
    'docs/atlas_vue_migration_plan.md',
    'docs/atlas_thinui_readiness.md',
]


def test_docs_track_state_and_safety_contract_for_vue17b() -> None:
    for path in DOCS:
        t = Path(path).read_text(encoding='utf-8')
        assert 'Completed UI PRs: PR-ATLAS-VUE-01 through PR-ATLAS-VUE-21' in t
        assert 'Current UI track: Vue defaultization complete' in t
        assert 'Planned UI track: return to PR-ATLAS-SCALE-93 automation track' in t
        assert 'Current automation track: PR-ATLAS-SCALE-93' in t
        assert 'legacy UI remains available via /ui/' in t
        assert 'runtime remains level_0_manual_only' in t
        assert 'Vue execution capability remains none' in t
