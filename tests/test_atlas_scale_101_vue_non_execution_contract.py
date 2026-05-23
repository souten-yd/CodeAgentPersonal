from pathlib import Path

def test_vue_remains_advisory_backend_authoritative_non_execution():
    t=Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text(encoding='utf-8').lower()
    assert 'backend workflow_state remains authoritative' in t
    assert 'not a readiness decision' in t
    assert 'not execution eligibility' in t
    assert '/api/atlas/level1/execute' not in t
