from fastapi.testclient import TestClient

from main import app


def test_scale_95_readiness_route_get_only() -> None:
    client = TestClient(app)
    assert client.get('/api/atlas/level1/readiness').status_code == 200
    for method_name in ('post', 'put', 'patch', 'delete'):
        response = getattr(client, method_name)('/api/atlas/level1/readiness')
        assert response.status_code == 405
