from fastapi.testclient import TestClient

from app.server import create_app


def test_evaluate_api_rejects_pool_id_path_traversal():
    c = TestClient(create_app())
    r = c.post('/api/atlas/evaluator/evaluate', json={"pool_id":"../x","trigger":"manual"})
    assert r.status_code == 400


def test_result_api_rejects_path_traversal():
    c = TestClient(create_app())
    r = c.get('/api/atlas/evaluator/results/../x/eval_aaa')
    assert r.status_code in (400, 404)


def test_evaluator_api_no_side_effect_events_strict(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    c = TestClient(create_app())
    r = c.post('/api/atlas/evaluator/evaluate', json={"pool_id":"p1","trigger":"manual"})
    assert r.status_code == 200
    dumped = str(r.json())
    for name in ["safe_apply_manual_started", "auto_safe_apply_started", "auto_verification_started", "verification_manual_started", "debug_review_auto_started", "patch_proposal_auto_started", "change_snapshot_restore_auto_started", "auto_rollback_started"]:
        assert name not in dumped
