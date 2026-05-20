from fastapi.testclient import TestClient
from app.server import create_app


def test_planpool_has_verification_plan():
    c=TestClient(create_app())
    r=c.post('/api/atlas/plan-pools', json={'input':'x','project_path':'/tmp/not-found-repo'})
    assert r.status_code==200
    body=r.json()['plan_pool']
    assert 'verification_plan' in body.get('metadata', {})
    for item in body.get('items', []):
        assert 'verification_hints' in (item.get('metadata') or {})


def test_repo_context_disabled_no_active_verification_plan(tmp_path):
    app=create_app(); app.state.atlas_ca_data_root=tmp_path; c=TestClient(app)
    r=c.post('/api/atlas/plan-pools', json={'input':'x','project_path':str(tmp_path), 'enable_repo_context':False})
    assert r.status_code==200
    assert 'verification_plan' not in r.json()['plan_pool'].get('metadata', {})
