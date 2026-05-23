from fastapi.testclient import TestClient
from main import app

def test_scale_96_runtime_safety_regression() -> None:
    payload=TestClient(app).get('/api/atlas/level1/readiness').json()
    assert payload['runtime_level']=='level_0_manual_only'
    assert payload['level1_execution_enabled'] is False
    assert payload['callable_execution_endpoint_enabled'] is False
    assert payload['vue_execution_controls_enabled'] is False
