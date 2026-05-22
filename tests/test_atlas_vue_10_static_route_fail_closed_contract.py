from fastapi.testclient import TestClient

from app.server import create_app


def test_fail_closed_when_dist_missing_and_no_ui_redirect() -> None:
    app = create_app()
    client = TestClient(app)
    for path in ['/atlas-next', '/atlas-next/', '/atlas-next/assets/app.js']:
        res = client.get(path)
        assert res.status_code == 404
        assert '/ui/' not in res.text


def test_path_traversal_blocked() -> None:
    app = create_app()
    client = TestClient(app)
    res = client.get('/atlas-next/../../main.py')
    assert res.status_code == 404
