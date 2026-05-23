from fastapi.testclient import TestClient
from main import app

def test_scale_96_readiness_route_get_only() -> None:
    c=TestClient(app)
    assert c.get('/api/atlas/level1/readiness').status_code==200
    for m in ('post','put','patch','delete'):
        assert getattr(c,m)('/api/atlas/level1/readiness').status_code==405
