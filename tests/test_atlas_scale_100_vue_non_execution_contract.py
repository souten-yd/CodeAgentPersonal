from pathlib import Path

def test_vue_non_execution_and_backend_authoritative_notes_present():
    t=Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text(encoding='utf-8').lower()
    assert 'backend workflow_state remains authoritative' in t
    assert 'not a readiness decision' in t
    assert 'not execution eligibility' in t
