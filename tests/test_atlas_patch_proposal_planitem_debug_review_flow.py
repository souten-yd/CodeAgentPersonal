from pathlib import Path

from fastapi.testclient import TestClient

import main

DASH = Path('web/js/atlas_dashboard.js').read_text(encoding='utf-8')


def _client(tmp_path):
    main.app.state.atlas_ca_data_dir = str(tmp_path)
    return TestClient(main.app)


def _create_pool(client):
    return client.post('/api/atlas/plan-pools', json={'input': 'debug review flow'}).json()


def _set_item_for_failed_draft_verification(client, pool_id: str, item_id: str, status: str = 'failed'):
    import json
    pool = client.get(f'/api/atlas/plan-pools/{pool_id}').json()['plan_pool']
    for item in pool['items']:
        if item['item_id'] == item_id:
            item.setdefault('metadata', {})['source'] = 'patch_proposal'
            item['metadata']['source_proposal_id'] = 'pp-001'
            item['metadata']['safe_apply'] = {'status': 'applied', 'source': 'patch_proposal', 'source_proposal_id': 'pp-001'}
            if status:
                item['metadata']['verification'] = {'status': status, 'stderr': 'failed', 'source': 'patch_proposal', 'source_proposal_id': 'pp-001'}
            item['status'] = 'failed' if status == 'failed' else 'completed'
    path = Path(client.app.state.atlas_ca_data_dir, 'atlas', 'plan_pools', f'{pool_id}.json')
    path.write_text(json.dumps(pool), encoding='utf-8')


def test_failed_draft_verification_appears_as_debug_review_candidate_contract():
    assert "verificationStatus === 'failed' || itemStatus === 'failed'" in DASH
    assert 'Patch Proposal Draft' in DASH
    assert 'Manual analysis only.' in DASH
    assert 'No patch proposal is generated automatically.' in DASH


def test_manual_debug_review_preserves_draft_source_metadata(tmp_path):
    c = _client(tmp_path)
    pool = _create_pool(c)
    item = pool['plan_pool']['items'][0]
    _set_item_for_failed_draft_verification(c, pool['pool_id'], item['item_id'])
    res = c.post('/api/atlas/debug-review/run', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'dr-flow'}).json()
    assert res['status'] == 'analyzed'
    after = c.get(f"/api/atlas/plan-pools/{pool['pool_id']}").json()['plan_pool']
    meta = next(i for i in after['items'] if i['item_id'] == item['item_id'])['metadata']['debug_review']
    assert meta['status'] == 'analyzed'
    assert meta['source'] == 'patch_proposal_planitem_draft'
    assert meta['source_proposal_id'] == 'pp-001'
    assert meta['manual_only'] is True
    assert meta['auto_patch_proposal'] is False


def test_debug_review_blocked_for_passed_verification(tmp_path):
    c = _client(tmp_path)
    pool = _create_pool(c)
    item = pool['plan_pool']['items'][0]
    _set_item_for_failed_draft_verification(c, pool['pool_id'], item['item_id'], status='passed')
    body = c.post('/api/atlas/debug-review/run', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'dr-pass'}).json()
    assert body['status'] == 'blocked'
    assert 'verification_not_failed' in body['warnings']


def test_debug_review_blocked_for_unverified_draft(tmp_path):
    c = _client(tmp_path)
    pool = _create_pool(c)
    item = pool['plan_pool']['items'][0]
    _set_item_for_failed_draft_verification(c, pool['pool_id'], item['item_id'], status='')
    body = c.post('/api/atlas/debug-review/run', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'dr-unverified'}).json()
    assert body['status'] == 'blocked'
    assert 'verification_not_failed' in body['warnings']
