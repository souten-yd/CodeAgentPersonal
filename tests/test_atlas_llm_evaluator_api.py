from fastapi.testclient import TestClient
from app.server import create_app


def test_policy_list_api():
    c = TestClient(create_app())
    r = c.get('/api/atlas/evaluator/policies')
    assert r.status_code == 200
    ids = {p['policy_id'] for p in r.json()['policies']}
    assert {'guarded_evaluator_v1','manual_review_only','strict_failure_guard'}.issubset(ids)


def test_result_api_rejects_path_traversal():
    c = TestClient(create_app())
    r = c.get('/api/atlas/evaluator/results/../x/eval_aaa')
    assert r.status_code in (400,404)
