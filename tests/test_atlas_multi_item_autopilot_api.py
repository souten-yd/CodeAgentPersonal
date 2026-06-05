from fastapi.testclient import TestClient
from app.server import create_app


def test_api_path_traversal_rejected():
    app = create_app()
    c = TestClient(app)
    r = c.get('/api/atlas/multi-item-autopilot/results/../x/auto_x')
    assert r.status_code in (400,404)
