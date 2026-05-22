from pathlib import Path


def test_vue_04_docs_contract() -> None:
    handoff = Path('docs/atlas_development_handoff.md').read_text(encoding='utf-8')
    roadmap = Path('docs/atlas_scale_master_roadmap.md').read_text(encoding='utf-8')
    migration = Path('docs/atlas_vue_migration_plan.md').read_text(encoding='utf-8')
    thinui = Path('docs/atlas_thinui_readiness.md').read_text(encoding='utf-8')
    docs = '\n'.join([handoff, roadmap, migration, thinui]).lower()

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

    roadmap_lower = roadmap.lower()
    assert '- pr-atlas-vue-04: safe backend workflow_state get adapter / static mount decision' in roadmap_lower
    assert 'current automation track pr:\n- pr-atlas-scale-93: level-1 guarded execution design checkpoint' in roadmap_lower
    assert 'current ui track: pr-atlas-vue-05: define stable read-only workflow_state backend contract' in roadmap_lower

    for deferred_reason in [
        'deferred because no stable dedicated read-only workflow_state + available_actions endpoint contract is finalized yet',
        'deferred because committed dist/static artifact strategy for `/atlas-next` is not locked yet',
    ]:
        assert deferred_reason in docs
