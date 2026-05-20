from fastapi.testclient import TestClient
from app.server import create_app

def test_planpool_has_packaging(tmp_path):
    app=create_app(); app.state.atlas_ca_data_root=str(tmp_path)
    c=TestClient(app)
    r=c.post('/api/atlas/plan-pools',json={"input":"g","project_path":str(tmp_path),"enable_repo_context":True})
    assert r.status_code==200
    md=r.json()['plan_pool']['metadata']
    assert 'planner_packaging_v2' in md and 'planner_context_text_v2' in md
