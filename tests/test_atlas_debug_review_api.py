from pathlib import Path

from fastapi.testclient import TestClient

import main
from agent.atlas_debug_review_schema import AtlasDebugReviewRequest


def _client(tmp_path):
    main.app.state.atlas_ca_data_dir = str(tmp_path)
    return TestClient(main.app)


def _create_pool(client):
    return client.post('/api/atlas/plan-pools', json={'input': 'debug review'}).json()


def _set_verification_failed(client, pool_id: str, item_id: str):
    data = client.get(f'/api/atlas/plan-pools/{pool_id}').json()['plan_pool']
    for item in data['items']:
        if item['item_id'] == item_id:
            item.setdefault('metadata', {})['verification'] = {
                'status': 'failed',
                'stderr': 'Traceback: failed test',
                'error_summary': 'verification failed in test suite',
            }
            item['status'] = 'failed'
    import json
    plan_pool_path = Path(client.app.state.atlas_ca_data_dir, 'atlas', 'plan_pools', f'{pool_id}.json')
    plan_pool_path.parent.mkdir(parents=True, exist_ok=True)
    plan_pool_path.write_text(json.dumps(data), encoding='utf-8')


def test_debug_review_route_exists(tmp_path):
    _client(tmp_path)
    paths = {r.path for r in main.app.routes}
    assert '/api/atlas/debug-review/run' in paths


def test_debug_review_requires_failed_verification(tmp_path):
    c = _client(tmp_path)
    pool = _create_pool(c)
    item = pool['plan_pool']['items'][0]
    res = c.post('/api/atlas/debug-review/run', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'r1'})
    assert res.status_code == 200
    assert res.json()['status'] == 'blocked'
    assert 'verification_not_failed' in res.json()['warnings']


def test_debug_review_analyzes_failed_verification(tmp_path):
    c = _client(tmp_path)
    pool = _create_pool(c)
    item = pool['plan_pool']['items'][0]
    _set_verification_failed(c, pool['pool_id'], item['item_id'])
    res = c.post('/api/atlas/debug-review/run', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'r2'})
    body = res.json()
    assert res.status_code == 200
    assert body['status'] == 'analyzed'
    assert body['debug_attempt'].get('root_cause_category')
    assert body['debug_attempt'].get('proposed_fix') or body['debug_attempt'].get('reusable_lesson')


def test_debug_review_record_saved_and_event(tmp_path):
    c = _client(tmp_path)
    pool = _create_pool(c)
    item = pool['plan_pool']['items'][0]
    _set_verification_failed(c, pool['pool_id'], item['item_id'])
    res = c.post('/api/atlas/debug-review/run', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'r3'})
    body = res.json()
    rec_json = Path(body['metadata']['debug_review_record_json'])
    rec_md = Path(body['metadata']['debug_review_record_md'])
    assert rec_json.exists() and rec_md.exists()
    event_files = list(Path(tmp_path).rglob('events.ndjson'))
    assert event_files
    events = '\n'.join(f.read_text(encoding='utf-8') for f in event_files)
    assert 'debug_review_manual_analyzed' in events
    md = rec_md.read_text(encoding='utf-8')
    assert 'No patch was generated.' in md
    assert 'No safe_apply was run.' in md
    assert 'No verification rerun was performed.' in md


def test_debug_review_updates_item_metadata(tmp_path):
    c = _client(tmp_path)
    pool = _create_pool(c)
    item = pool['plan_pool']['items'][0]
    _set_verification_failed(c, pool['pool_id'], item['item_id'])
    c.post('/api/atlas/debug-review/run', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'r4'})
    after = c.get(f"/api/atlas/plan-pools/{pool['pool_id']}").json()['plan_pool']
    meta = next(i for i in after['items'] if i['item_id'] == item['item_id'])['metadata']['debug_review']
    assert meta['status'] == 'analyzed'
    assert meta.get('root_cause_category')
    assert meta.get('proposed_fix') is not None
    assert meta.get('debug_notes_path')


def test_debug_review_response_includes_recovery_orchestration_continuation(tmp_path):
    c = _client(tmp_path)
    pool = _create_pool(c)
    item = pool['plan_pool']['items'][0]
    _set_verification_failed(c, pool['pool_id'], item['item_id'])
    body = c.post('/api/atlas/debug-review/run', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'r5'}).json()
    assert body.get('recovery_summary')
    assert body.get('orchestration_summary')
    assert body.get('continuation_prompt')
    assert body['orchestration_summary'].get('phase') or body['orchestration_summary'].get('next_action')


def test_debug_review_does_not_run_patch_safe_apply_or_verification():
    src_api = Path('app/api/atlas_pipeline.py').read_text(encoding='utf-8')
    route_src = src_api.split('@router.post("/debug-review/run"', 1)[1].split('@router.get("/recovery/latest"', 1)[0]
    for forbidden in ('execute_safe_apply', 'runVerification', 'TestCommandRunner', 'ImplementationExecutor'):
        assert forbidden not in route_src


def test_debug_review_schema_has_no_patch_or_command_fields():
    fields = set(AtlasDebugReviewRequest.model_fields.keys())
    for forbidden in ('patch', 'command', 'shell', 'apply'):
        assert forbidden not in fields


def test_debug_review_service_has_no_forbidden_tokens():
    source = Path('agent/atlas_debug_review_service.py').read_text(encoding='utf-8')
    for forbidden in ('subprocess', 'shell=True', 'safe_apply(', 'execute_safe_apply', 'TestCommandRunner(', 'DeepResearch', 'run_command(', 'unlink('):
        assert forbidden not in source


def test_no_batch_debug_review_route(tmp_path):
    c = _client(tmp_path)
    assert c.post('/api/atlas/debug-review/run', json={'pool_id': 'x', 'item_id': 'y'}).status_code in {200, 400}
    assert c.post('/api/atlas/debug-review/batch', json={}).status_code in {404, 405}
