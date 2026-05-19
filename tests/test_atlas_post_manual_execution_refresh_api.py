from fastapi.testclient import TestClient
from main import app

def test_api_path_traversal_rejected():
    c=TestClient(app)
    r=c.get('/api/atlas/post-manual-execution-refresh/results/../x/postexec_1')
    assert r.status_code in {400,404}
