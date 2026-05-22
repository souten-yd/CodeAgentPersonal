from pathlib import Path


def test_vue_11_docs_contract() -> None:
    docs = '\n'.join([
        Path('docs/atlas_scale_master_roadmap.md').read_text(encoding='utf-8').lower(),
        Path('docs/atlas_vue_migration_plan.md').read_text(encoding='utf-8').lower(),
        Path('docs/atlas_thinui_readiness.md').read_text(encoding='utf-8').lower(),
        Path('docs/atlas_development_handoff.md').read_text(encoding='utf-8').lower(),
    ])
    for s in [
        'pr-atlas-vue-11',
        'current ui track: pr-atlas-vue-12',
        'pr-atlas-scale-93',
        'existing `ui.html` remains default',
        'parallel/read-only/not default',
        'guarded, dist-backed, fail-closed',
        'get-only',
        'metadata',
        'backend workflow state remains authoritative',
        'no vue execution capability exists',
    ]:
        assert s in docs
