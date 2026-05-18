from fastapi.testclient import TestClient
from app.server import create_app

def test_api_path_traversal_rejected():
    c = TestClient(create_app())
    r = c.get('/api/atlas/bounded-retry/results/../x/retry_x')
    assert r.status_code in (400,404)
