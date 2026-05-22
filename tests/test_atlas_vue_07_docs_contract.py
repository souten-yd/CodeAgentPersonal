from pathlib import Path


def test_vue_07_docs_contract() -> None:
    docs = '\n'.join([
        Path('docs/atlas_scale_master_roadmap.md').read_text(encoding='utf-8'),
        Path('docs/atlas_vue_migration_plan.md').read_text(encoding='utf-8'),
        Path('docs/atlas_development_handoff.md').read_text(encoding='utf-8'),
        Path('docs/atlas_thinui_readiness.md').read_text(encoding='utf-8'),
    ]).lower()

    assert 'pr-atlas-vue-07 completed' in docs
    assert ('current ui track: pr-atlas-vue-09' in docs) or ('current ui track: pr-atlas-vue-10' in docs)
    assert 'pr-atlas-scale-93 remains automation track current' in docs or 'current automation track remains pr-atlas-scale-93' in docs
    for required in [
        'read-only parity tests',
        'visual refinement',
        'existing ui.html remains default',
        'static mount remains deferred',
        'backend workflow state remains authoritative',
        'available_actions are metadata only',
        'does not compute execution eligibility',
        'does not call mutation endpoints',
    ]:
        assert required in docs
