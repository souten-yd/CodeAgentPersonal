from pathlib import Path


def test_vue16_docs_track_and_safety_contract() -> None:
    docs = '\n'.join(Path(p).read_text(encoding='utf-8') for p in [
        'docs/atlas_development_handoff.md',
        'docs/atlas_scale_master_roadmap.md',
        'docs/atlas_vue_migration_plan.md',
        'docs/atlas_thinui_readiness.md',
    ])
    for marker in [
        'PR-ATLAS-VUE-16 completed',
        'Current UI track: PR-ATLAS-VUE-17',
        'Planned UI track: PR-ATLAS-VUE-17 through PR-ATLAS-VUE-21',
        'PR-ATLAS-SCALE-93',
        'ui.html remains default until PR-ATLAS-VUE-21',
        'planning_metadata_only',
        'runtime remains level_0_manual_only',
        'execution capability remains none',
    ]:
        assert marker in docs
