from fastapi.testclient import TestClient
from main import app

def test_api_build_repo_index(tmp_path):
    (tmp_path/'a.py').write_text('def x():\n pass\n')
    c=TestClient(app)
    r=c.post('/api/atlas/repo-index/build',json={'project_path':str(tmp_path)})
    assert r.status_code==200
