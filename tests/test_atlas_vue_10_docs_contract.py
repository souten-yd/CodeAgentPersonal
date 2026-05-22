from pathlib import Path


def test_vue_10_docs_contract() -> None:
    docs = '\n'.join([
        Path('docs/atlas_scale_master_roadmap.md').read_text(encoding='utf-8').lower(),
        Path('docs/atlas_vue_migration_plan.md').read_text(encoding='utf-8').lower(),
        Path('docs/atlas_thinui_readiness.md').read_text(encoding='utf-8').lower(),
        Path('docs/atlas_development_handoff.md').read_text(encoding='utf-8').lower(),
    ])
    for s in [
        'pr-atlas-vue-10',
        'current ui track: pr-atlas-vue-11',
        'pr-atlas-scale-93: level-1 guarded execution design checkpoint',
        'dist',
        'fail closed',
        'must never replace `/`',
        'must never replace `/ui.html`',
        'existing `ui.html` remains default',
        'read-only',
        'backend workflow state remains authoritative',
        'available_actions',
        'does not compute execution eligibility',
        'does not call mutation endpoints',
    ]:
        assert s in docs
