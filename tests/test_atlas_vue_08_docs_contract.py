from pathlib import Path


def test_vue_08_docs_contract() -> None:
    roadmap = Path('docs/atlas_scale_master_roadmap.md').read_text(encoding='utf-8').lower()
    docs = '\n'.join([
        roadmap,
        Path('docs/atlas_vue_migration_plan.md').read_text(encoding='utf-8').lower(),
        Path('docs/atlas_development_handoff.md').read_text(encoding='utf-8').lower(),
        Path('docs/atlas_thinui_readiness.md').read_text(encoding='utf-8').lower(),
    ])
    assert 'pr-atlas-vue-08: safe static mount/dist strategy' in roadmap
    assert ('current ui track: pr-atlas-vue-09: atlas next read-only smoke route / build artifact policy' in roadmap) or ('current ui track: pr-atlas-vue-10: optional guarded /atlas-next preview route hardening' in roadmap)
    assert 'pr-atlas-scale-93: level-1 guarded execution design checkpoint' in roadmap
    for required in [
        'safe static mount / dist strategy',
        'static mount decision in this pr remains deferred',
                'raw vite source files must not be served as production ui',
        '/atlas-next',
        'existing `ui.html` remains the default ui',
        'parallel/read-only/not default',
        'backend workflow state remains authoritative',
        'available_actions are metadata only',
        'does not compute execution eligibility',
        'does not call mutation endpoints',
    ]:
        assert required in docs
