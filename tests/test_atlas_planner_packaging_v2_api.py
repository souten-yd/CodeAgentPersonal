from fastapi.testclient import TestClient
from app.server import create_app

def test_endpoint_200_and_flags(tmp_path):
    app=create_app(); app.state.atlas_ca_data_root=str(tmp_path)
    c=TestClient(app)
    r=c.post('/api/atlas/repo-context/planner-packaging-v2',json={"project_path":str(tmp_path)})
    assert r.status_code==200
    b=r.json(); assert b.get('status') is not None and 'planner_context_text' in b and 'context_sections' in b
    assert b['metadata']['advisory_only'] is True and b['metadata']['shell_executed'] is False

def test_endpoint_reject_file(tmp_path):
    app=create_app()
    f=tmp_path/'a.txt'; f.write_text('x')
    c=TestClient(app)
    r=c.post('/api/atlas/repo-context/planner-packaging-v2',json={"project_path":str(f)})
    assert r.status_code==400
