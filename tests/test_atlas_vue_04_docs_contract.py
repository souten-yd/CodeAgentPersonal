from pathlib import Path


def test_vue_04_docs_contract() -> None:
    docs = '\n'.join([
        Path('docs/atlas_development_handoff.md').read_text(encoding='utf-8'),
        Path('docs/atlas_scale_master_roadmap.md').read_text(encoding='utf-8'),
        Path('docs/atlas_vue_migration_plan.md').read_text(encoding='utf-8'),
        Path('docs/atlas_thinui_readiness.md').read_text(encoding='utf-8'),
    ]).lower()

    for required in [
        'pr-atlas-vue-04',
        'pr-atlas-scale-93',
        'pr-atlas-vue-05',
        'read-only',
        'ui.html remains default',
        'backend workflow state remains authoritative',
        'metadata-only',
        'does not compute execution eligibility',
        'does not call mutation endpoints',
        'safe get adapter',
        'static mount',
    ]:
        assert required in docs
