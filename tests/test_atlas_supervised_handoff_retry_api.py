from fastapi.testclient import TestClient
from app.server import create_app

def test_no_task_agent_routes():
    app=create_app(); c=TestClient(app)
    assert c.get('/api/task/x').status_code in {404,405}
    assert c.get('/api/agent/x').status_code in {404,405}

def test_safe_apply_execution_id_prefix_strict():
    app=create_app(); c=TestClient(app)
    bad={"pool_id":"p1","item_id":"i1","safe_apply_execution_id":"safe_x","verification_run_id":"verifyhandoff_x"}
    r=c.post('/api/atlas/supervised-handoff-retry/run',json=bad)
    assert r.status_code==400
    ok={"pool_id":"p1","item_id":"i1","safe_apply_execution_id":"safehandoff_x","verification_run_id":"verifyhandoff_x"}
    # may fail later on missing artifacts; we only validate prefix acceptance
    r2=c.post('/api/atlas/supervised-handoff-retry/run',json=ok)
    assert r2.status_code!=400
