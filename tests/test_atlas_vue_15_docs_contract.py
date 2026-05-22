from pathlib import Path


def test_vue_15_docs_contract() -> None:
    docs = '\n'.join(Path(p).read_text(encoding='utf-8').lower() for p in [
        'docs/atlas_development_handoff.md',
        'docs/atlas_scale_master_roadmap.md',
        'docs/atlas_vue_migration_plan.md',
        'docs/atlas_thinui_readiness.md',
    ])
    for needle in [
        'pr-atlas-vue-15 completed',
        'current ui track',
        'pr-atlas-vue-16',
        'pr-atlas-scale-93',
        'ui.html remains default until pr-atlas-vue-21',
        'backend workflow_state remains authoritative',
    ]:
        assert needle in docs
