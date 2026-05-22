from pathlib import Path


def test_vue_05_workflow_state_contract_docs_tracks() -> None:
    roadmap = Path('docs/atlas_scale_master_roadmap.md').read_text(encoding='utf-8')
    assert '- PR-ATLAS-VUE-05: Define stable read-only workflow_state backend contract' in roadmap
    assert 'Current UI track: PR-ATLAS-VUE-07: Vue read-only parity tests / visual refinement' in roadmap
    assert 'Current automation track remains PR-ATLAS-SCALE-93: Level-1 guarded execution design checkpoint' in roadmap


def test_vue_05_workflow_state_contract_docs_guardrails() -> None:
    plan = Path('docs/atlas_vue_migration_plan.md').read_text(encoding='utf-8')
    assert 'Current automation track remains `PR-ATLAS-SCALE-93: Level-1 guarded execution design checkpoint`.' in plan
    assert 'not default' in plan.lower()
    assert 'read-only' in plan.lower()
