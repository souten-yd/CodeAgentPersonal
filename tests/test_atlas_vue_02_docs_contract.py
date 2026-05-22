from pathlib import Path


def test_vue_02_docs_contract() -> None:
    roadmap = Path('docs/atlas_scale_master_roadmap.md').read_text(encoding='utf-8').lower()
    migration = Path('docs/atlas_vue_migration_plan.md').read_text(encoding='utf-8').lower()
    docs = roadmap + '\n' + migration

    assert 'pr-atlas-vue-02: safe static serving / read-only workflow_state adapter hardening' in roadmap
    assert 'current ui track: pr-atlas-vue-03: read-only workflow cards / backend state parity hardening' in roadmap
    assert 'pr-atlas-scale-93: level-1 guarded execution design checkpoint' in roadmap

    assert 'static mount remains deferred' in roadmap
    assert 'existing ui.html remains default' in docs
    assert 'read-only' in docs
    assert 'not default' in docs
    assert 'no execution' in docs
    assert 'backend workflow state remains authoritative' in docs
    assert 'does not call mutation endpoints' in docs
    assert 'available actions are metadata only' in docs
