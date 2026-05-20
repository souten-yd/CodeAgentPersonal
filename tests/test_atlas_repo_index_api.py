from fastapi.testclient import TestClient
from main import app

def test_api_build_repo_index(tmp_path):
    (tmp_path/'a.py').write_text('def x():\n pass\n'); c=TestClient(app)
    assert c.post('/api/atlas/repo-index/build',json={'project_path':str(tmp_path)}).status_code==200

def test_api_result_not_found(tmp_path):
    c=TestClient(app); r=c.get('/api/atlas/repo-index/results/12345678/repoindex_deadbeef'); assert r.status_code==404

def test_api_project_hash_validation(tmp_path):
    c=TestClient(app); r=c.get('/api/atlas/repo-index/results/nothex/repoindex_deadbeef'); assert r.status_code==400
