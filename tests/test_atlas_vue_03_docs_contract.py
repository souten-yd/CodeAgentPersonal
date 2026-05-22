from pathlib import Path


def test_vue_03_docs_contract() -> None:
    roadmap = Path('docs/atlas_scale_master_roadmap.md').read_text(encoding='utf-8').lower()
    migration = Path('docs/atlas_vue_migration_plan.md').read_text(encoding='utf-8').lower()
    docs = roadmap + '\n' + migration

    assert 'pr-atlas-vue-03: read-only workflow cards / backend state parity hardening' in roadmap
    assert 'current ui track: pr-atlas-vue-04: safe backend workflow_state get adapter / static mount decision' in roadmap
    assert 'pr-atlas-scale-93: level-1 guarded execution design checkpoint' in roadmap

    for required in [
        'read-only',
        'not default',
        'no execution',
        'existing ui.html remains default',
        'backend workflow state remains authoritative',
        'available actions are metadata only',
        'static mount remains deferred',
    ]:
        assert required in docs
