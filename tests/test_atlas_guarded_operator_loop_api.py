from fastapi.testclient import TestClient
from main import app

def test_mode_allowlist():
    c=TestClient(app)
    r=c.post('/api/atlas/guarded-operator-loop/run',json={'pool_id':'p1','mode':'bad'})
    assert r.status_code==400
