from pathlib import Path

from fastapi.testclient import TestClient

import main


def _client(tmp_path):
    main.app.state.atlas_ca_data_dir = str(tmp_path)
    return TestClient(main.app)


def _create(client):
    r = client.post('/api/atlas/plan-pools', json={'input': 'approval flow'})
    return r.json()


def _get_first_item_id(created):
    return created['plan_pool']['items'][0]['item_id']


def test_get_approvals_pending_count_matches_required_items(tmp_path):
    c = _client(tmp_path)
    created = _create(c)
    item_id = _get_first_item_id(created)

    c.post('/api/atlas/approvals/decide', json={'pool_id': created['pool_id'], 'item_id': item_id, 'decision': 'approved'})
    c.post('/api/atlas/approvals/decide', json={'pool_id': created['pool_id'], 'item_id': item_id, 'decision': 'needs_revision'})

    created2 = _create(c)
    r = c.get(f"/api/atlas/approvals/pools/{created2['pool_id']}")
    assert r.status_code == 200
    body = r.json()
    assert body['pending_count'] == 1
    assert len(body['approval_required_items']) == 1


def test_approved_item_removed_from_pending_count(tmp_path):
    c = _client(tmp_path)
    created = _create(c)
    item_id = _get_first_item_id(created)

    approve = c.post('/api/atlas/approvals/decide', json={'pool_id': created['pool_id'], 'item_id': item_id, 'decision': 'approved'})
    assert approve.status_code == 200

    r = c.get(f"/api/atlas/approvals/pools/{created['pool_id']}")
    body = r.json()
    assert body['pending_count'] == 0
    assert body['approved_count'] == 1
    assert body['approval_required_items'] == []

    pool = c.get(f"/api/atlas/plan-pools/{created['pool_id']}").json()
    assert pool['items'][0]['metadata']['approval']['decision'] == 'approved'


def test_rejected_item_removed_from_pending_and_counted(tmp_path):
    c = _client(tmp_path)
    created = _create(c)
    item_id = _get_first_item_id(created)

    reject = c.post('/api/atlas/approvals/decide', json={'pool_id': created['pool_id'], 'item_id': item_id, 'decision': 'rejected'})
    assert reject.status_code == 200

    r = c.get(f"/api/atlas/approvals/pools/{created['pool_id']}")
    body = r.json()
    assert body['pending_count'] == 0
    assert body['rejected_count'] == 1
    assert body['approval_required_items'] == []

    pool = c.get(f"/api/atlas/plan-pools/{created['pool_id']}").json()
    assert pool['items'][0]['status'] == 'blocked'


def test_needs_revision_counted_separately_if_supported(tmp_path):
    c = _client(tmp_path)
    created = _create(c)
    item_id = _get_first_item_id(created)

    res = c.post('/api/atlas/approvals/decide', json={'pool_id': created['pool_id'], 'item_id': item_id, 'decision': 'needs_revision'})
    assert res.status_code == 200

    r = c.get(f"/api/atlas/approvals/pools/{created['pool_id']}")
    body = r.json()
    assert body['pending_count'] == 0
    assert body['needs_revision_count'] == 1

    pool = c.get(f"/api/atlas/plan-pools/{created['pool_id']}").json()
    assert pool['items'][0]['status'] == 'needs_revision'


def test_approval_record_saved_to_journal(tmp_path):
    c = _client(tmp_path)
    created = _create(c)
    item_id = _get_first_item_id(created)
    body = c.post('/api/atlas/approvals/decide', json={'pool_id': created['pool_id'], 'item_id': item_id, 'decision': 'rejected'}).json()
    aid = body['approval_record']['approval_id']
    base = Path(tmp_path) / 'atlas' / 'workspaces' / 'default' / 'plan_pools' / created['pool_id'] / 'approvals'
    assert (base / f'{aid}.json').exists()
    assert (base / f'{aid}.md').exists()


def test_approval_api_does_not_execute_safe_apply():
    for fp in ('app/api/atlas_pipeline.py', 'agent/atlas_approval_service.py'):
        text = Path(fp).read_text(encoding='utf-8')
        for forbidden in ('safe_apply(', 'TestCommandRunner(', 'DebugLoopRunner(', 'DeepResearch', 'subprocess', 'run_command('):
            assert forbidden not in text
