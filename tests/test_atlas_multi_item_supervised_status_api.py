from fastapi.testclient import TestClient
from app.server import create_app

def test_api_path_traversal_rejected():
    c=TestClient(create_app())
    r=c.post('/api/atlas/multi-item-supervised-status/build', json={'pool_id':'../x'})
    assert r.status_code==400
