from fastapi.testclient import TestClient
from main import app


def test_scale_96_readiness_diagnostics_contract() -> None:
    payload = TestClient(app).get('/api/atlas/level1/readiness').json()
    assert isinstance(payload.get('gate_source_map'), list)
    assert isinstance(payload.get('evidence_summary'), dict)
    assert payload['mutation_performed'] is False
    assert payload['execution_performed'] is False
    assert payload['advisory_only'] is True
    assert payload['missing_evidence_count'] >= 0
