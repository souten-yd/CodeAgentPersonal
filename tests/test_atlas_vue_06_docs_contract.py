from pathlib import Path


def test_vue_06_docs_contract() -> None:
    docs = '\n'.join([
        Path('docs/atlas_scale_master_roadmap.md').read_text(encoding='utf-8'),
        Path('docs/atlas_vue_migration_plan.md').read_text(encoding='utf-8'),
        Path('docs/atlas_development_handoff.md').read_text(encoding='utf-8'),
        Path('docs/atlas_thinui_readiness.md').read_text(encoding='utf-8'),
    ]).lower()
    assert 'pr-atlas-vue-06: bind vue read-only adapter to stable get workflow_state contract' in docs
    assert ('current ui track: pr-atlas-vue-07: vue read-only parity tests / visual refinement' in docs) or ('current ui track: pr-atlas-vue-08: safe static mount/dist strategy' in docs)
    assert 'pr-atlas-scale-93: level-1 guarded execution design checkpoint' in docs
    assert 'get /api/atlas/workflow-state/read-only' in docs
    assert 'get-only' in docs
    assert 'fallback' in docs
    assert 'metadata only' in docs
    assert 'disabled/read-only' in docs or 'disabled' in docs
    assert 'static mount remains deferred' in docs or 'static mount deferred' in docs
    assert 'existing ui.html remains default' in docs
    assert 'backend workflow state remains authoritative' in docs
    assert 'not default' in docs
    assert 'does not compute execution eligibility' in docs
    assert 'does not call mutation endpoints' in docs
