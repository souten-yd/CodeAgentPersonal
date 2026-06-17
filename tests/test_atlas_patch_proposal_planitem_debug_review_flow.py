from pathlib import Path

from fastapi.testclient import TestClient

import main

DASH = Path('web/js/atlas_dashboard.js').read_text(encoding='utf-8')


def _client(tmp_path):
    main.app.state.atlas_ca_data_dir = str(tmp_path)
    return TestClient(main.app)


def _create_pool(client):
    return client.post('/api/atlas/plan-pools?sync=1', json={'plan_payload': {'implementation_steps': [{'step_id': 'step_001', 'title': 'Step', 'action_type': 'update', 'target_files': ['README.md']}]}, 'input': 'debug review flow'}).json()


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
    res = c.post('/api/atlas/debug-review/run?sync=1', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'dr-flow'}).json()
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
    body = c.post('/api/atlas/debug-review/run?sync=1', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'dr-pass'}).json()
    assert body['status'] == 'blocked'
    assert 'verification_not_failed' in body['warnings']


def test_debug_review_blocked_for_unverified_draft(tmp_path):
    c = _client(tmp_path)
    pool = _create_pool(c)
    item = pool['plan_pool']['items'][0]
    _set_item_for_failed_draft_verification(c, pool['pool_id'], item['item_id'], status='')
    body = c.post('/api/atlas/debug-review/run?sync=1', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'dr-unverified'}).json()
    assert body['status'] == 'blocked'
    assert 'verification_not_failed' in body['warnings']


def test_debug_review_does_not_auto_generate_patch_proposal_event_or_metadata(tmp_path):
    c = _client(tmp_path)
    pool = _create_pool(c)
    item = pool['plan_pool']['items'][0]
    _set_item_for_failed_draft_verification(c, pool['pool_id'], item['item_id'])

    # ensure debug review target item starts with no patch_proposal metadata
    import json
    path = Path(c.app.state.atlas_ca_data_dir, 'atlas', 'plan_pools', f"{pool['pool_id']}.json")
    saved = json.loads(path.read_text(encoding='utf-8'))
    for saved_item in saved['items']:
        if saved_item['item_id'] == item['item_id']:
            saved_item.setdefault('metadata', {}).pop('patch_proposal', None)
    path.write_text(json.dumps(saved), encoding='utf-8')

    res = c.post('/api/atlas/debug-review/run?sync=1', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'dr-no-auto'}).json()
    assert res['status'] == 'analyzed'

    events_path = Path(c.app.state.atlas_ca_data_dir, 'atlas', 'pipeline_runs', 'dr-no-auto', 'events.ndjson')
    events_text = events_path.read_text(encoding='utf-8') if events_path.exists() else ''
    assert 'patch_proposal_manual_started' not in events_text
    assert 'patch_proposal_manual_proposed' not in events_text
    assert 'safe_apply_manual_started' not in events_text
    assert 'verification_manual_started' not in events_text

    after = c.get(f"/api/atlas/plan-pools/{pool['pool_id']}").json()['plan_pool']
    target = next(i for i in after['items'] if i['item_id'] == item['item_id'])
    assert target.get('metadata', {}).get('patch_proposal') in (None, {})


def test_debug_review_response_has_manual_next_step_but_no_auto_patch(tmp_path):
    c = _client(tmp_path)
    pool = _create_pool(c)
    item = pool['plan_pool']['items'][0]
    _set_item_for_failed_draft_verification(c, pool['pool_id'], item['item_id'])

    res = c.post('/api/atlas/debug-review/run?sync=1', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'dr-next-step'}).json()
    assert res['status'] == 'analyzed'
    joined = str(res.get('continuation_prompt', '')) + str(res.get('metadata', ''))
    assert ('patch proposal' in joined.lower()) or ('manual' in joined.lower())
    debug_meta = res.get('item', {}).get('metadata', {}).get('debug_review', {})
    assert 'patch_proposal_result' not in debug_meta
    assert 'proposal_id' not in debug_meta
    assert 'patch proposal result' not in str(debug_meta).lower()


def test_no_batch_debug_review_route_still_absent(tmp_path):
    c = _client(tmp_path)
    pool = _create_pool(c)
    item = pool['plan_pool']['items'][0]
    _set_item_for_failed_draft_verification(c, pool['pool_id'], item['item_id'])
    ok = c.post('/api/atlas/debug-review/run?sync=1', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'dr-route'})
    assert ok.status_code == 200
    missing = c.post('/api/atlas/debug-review/batch', json={'pool_id': pool['pool_id']})
    assert missing.status_code == 404


def _snippet_between(source: str, start_token: str, end_token: str) -> str:
    start = source.index(start_token)
    end = source.find(end_token, start)
    if end == -1:
        end = min(len(source), start + 2000)
    return source[start:end]


def test_debug_review_flow_source_has_no_auto_generation_tokens():
    dash = Path('web/js/atlas_dashboard.js').read_text(encoding='utf-8')
    api = Path('app/api/atlas_pipeline.py').read_text(encoding='utf-8')

    dash_snippet = _snippet_between(dash, 'async function runDebugReview', 'async function renderDebugReviewCandidates')
    api_snippet = _snippet_between(api, 'def run_debug_review(', 'def generate_patch_proposal(')
    combined = dash_snippet + '\n' + api_snippet

    forbidden = (
        'generatePatchProposal(',
        'patch_proposal_manual_started',
        'executeSafeApply(',
        'runVerification(',
        'TestCommandRunner(',
        'subprocess',
        'shell=True',
        'run_command(',
        'DeepResearch',
    )
    for token in forbidden:
        assert token not in combined
