from pathlib import Path

from fastapi.testclient import TestClient

import main
from agent.atlas_patch_proposal_schema import AtlasPatchProposalRequest


def _client(tmp_path):
    main.app.state.atlas_ca_data_dir = str(tmp_path)
    main.app.state.atlas_llm_json_fn = None
    return TestClient(main.app)


def _create_pool(c):
    return c.post('/api/atlas/plan-pools', json={'input': 'patch proposal'}).json()


def _set_debug_review(c, pool_id, item_id, analyzed=True):
    data = c.get(f'/api/atlas/plan-pools/{pool_id}').json()['plan_pool']
    for item in data['items']:
        if item['item_id'] == item_id:
            item.setdefault('metadata', {})['debug_review'] = {
                'status': 'analyzed' if analyzed else 'failed',
                'root_cause_category': 'test_failure',
                'proposed_fix': 'Adjust failing assertion and update guard logic.',
            }
    import json
    path = Path(c.app.state.atlas_ca_data_dir, 'atlas', 'plan_pools', f'{pool_id}.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding='utf-8')


def test_patch_proposal_requires_debug_review_analyzed(tmp_path):
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]
    body = c.post('/api/atlas/patch-proposals/generate', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'r1'}).json()
    assert body['status'] == 'blocked' and 'debug_review_not_analyzed' in body['warnings']


def test_patch_proposal_generates_from_debug_review_with_fallback(tmp_path):
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]; _set_debug_review(c, pool['pool_id'], item['item_id'])
    body = c.post('/api/atlas/patch-proposals/generate', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'r2'}).json()
    assert body['status'] == 'proposed'
    assert body['proposal']['proposed_fix'] and body['proposal']['target_files'] is not None
    assert body['proposal']['summary'] or body['proposal']['title']
    assert body['proposal'].get('warnings') is not None


def test_patch_proposal_uses_injected_llm_json_fn(tmp_path):
    c = _client(tmp_path)
    c.app.state.atlas_llm_json_fn = lambda s, u: {'summary': 'from llm', 'proposed_fix': 'llm fix', 'target_files': ['a.py'], 'risk_level': 'low'}
    pool = _create_pool(c); item = pool['plan_pool']['items'][0]; _set_debug_review(c, pool['pool_id'], item['item_id'])
    body = c.post('/api/atlas/patch-proposals/generate', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'r3'}).json()
    assert body['status'] == 'proposed' and body['proposal']['summary'] == 'from llm' and body['proposal']['risk_level'] == 'low'


def test_patch_proposal_record_saved_and_event(tmp_path):
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]; _set_debug_review(c, pool['pool_id'], item['item_id'])
    body = c.post('/api/atlas/patch-proposals/generate', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'r4'}).json()
    assert Path(body['proposal_json_path']).exists() and Path(body['proposal_md_path']).exists()
    events = '\n'.join(p.read_text(encoding='utf-8') for p in Path(tmp_path).rglob('events.ndjson'))
    assert 'patch_proposal_manual_proposed' in events
    md = Path(body['proposal_md_path']).read_text(encoding='utf-8')
    assert 'No patch was applied.' in md and 'No safe_apply was run.' in md and 'No verification rerun was performed.' in md


def test_patch_proposal_updates_item_metadata(tmp_path):
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]; _set_debug_review(c, pool['pool_id'], item['item_id'])
    c.post('/api/atlas/patch-proposals/generate', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'r5'})
    after = c.get(f"/api/atlas/plan-pools/{pool['pool_id']}").json()['plan_pool']
    meta = next(i for i in after['items'] if i['item_id'] == item['item_id'])['metadata']['patch_proposal']
    assert meta['status'] == 'proposed' and meta['proposal_json_path'] and meta['proposal_md_path']


def test_patch_proposal_response_includes_recovery_orchestration_continuation(tmp_path):
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]; _set_debug_review(c, pool['pool_id'], item['item_id'])
    body = c.post('/api/atlas/patch-proposals/generate', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'r6'}).json()
    assert body.get('recovery_summary') and body.get('orchestration_summary') and body.get('continuation_prompt')


def test_patch_proposal_does_not_apply_or_verify():
    src = Path('agent/atlas_patch_proposal_service.py').read_text(encoding='utf-8')
    for t in ('safe_apply(', 'execute_safe_apply', 'runVerification', 'TestCommandRunner(', 'ImplementationExecutor', 'subprocess', 'shell=True', 'run_command('):
        assert t not in src


def test_no_patch_apply_or_batch_routes(tmp_path):
    c = _client(tmp_path)
    assert c.post('/api/atlas/patch-proposals/generate', json={'pool_id': 'x', 'item_id': 'y'}).status_code in {200, 400}
    assert c.post('/api/atlas/patch-proposals/apply', json={}).status_code in {404, 405}
    assert c.post('/api/atlas/patch-proposals/batch', json={}).status_code in {404, 405}


def test_patch_proposal_request_has_no_patch_command_apply_fields():
    fields = set(AtlasPatchProposalRequest.model_fields.keys())
    for forbidden in ('patch', 'command', 'apply', 'shell', 'execute'):
        assert forbidden not in fields


def test_patch_proposal_ignores_llm_status_applied(tmp_path):
    c = _client(tmp_path)
    c.app.state.atlas_llm_json_fn = lambda s, u: {
        'status': 'applied',
        'proposal_id': 'malicious',
        'pool_id': 'other',
        'item_id': 'other_item',
        'run_id': 'other_run',
        'summary': 'from llm',
        'proposed_fix': 'safe proposal',
    }
    pool = _create_pool(c); item = pool['plan_pool']['items'][0]; _set_debug_review(c, pool['pool_id'], item['item_id'])
    body = c.post('/api/atlas/patch-proposals/generate', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'r7'}).json()
    assert body['status'] == 'proposed'
    assert body['proposal']['status'] == 'proposed'
    assert body['proposal']['pool_id'] == pool['pool_id']
    assert body['proposal']['item_id'] == item['item_id']
    assert body['proposal']['run_id'] == 'r7'
    assert 'llm_untrusted_fields_ignored' in body['proposal']['warnings']


def test_patch_proposal_normalizes_invalid_risk_level(tmp_path):
    c = _client(tmp_path)
    c.app.state.atlas_llm_json_fn = lambda s, u: {'risk_level': 'please_apply_now', 'proposed_fix': 'x'}
    pool = _create_pool(c); item = pool['plan_pool']['items'][0]; _set_debug_review(c, pool['pool_id'], item['item_id'])
    body = c.post('/api/atlas/patch-proposals/generate', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'r8'}).json()
    assert body['proposal']['risk_level'] == 'medium'
    assert 'llm_risk_level_normalized' in body['proposal']['warnings']


def test_patch_proposal_filters_unsafe_target_files(tmp_path):
    c = _client(tmp_path)
    c.app.state.atlas_llm_json_fn = lambda s, u: {'target_files': ['../secret', '/etc/passwd', 'safe.py'], 'proposed_fix': 'x'}
    pool = _create_pool(c); item = pool['plan_pool']['items'][0]; _set_debug_review(c, pool['pool_id'], item['item_id'])
    body = c.post('/api/atlas/patch-proposals/generate', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'r9'}).json()
    assert body['proposal']['target_files'] == ['safe.py']
    assert 'unsafe_target_files_ignored' in body['proposal']['warnings']


def test_patch_proposal_truncates_large_diff_preview(tmp_path):
    c = _client(tmp_path)
    c.app.state.atlas_llm_json_fn = lambda s, u: {'unified_diff_preview': 'x' * 20000, 'proposed_fix': 'x'}
    pool = _create_pool(c); item = pool['plan_pool']['items'][0]; _set_debug_review(c, pool['pool_id'], item['item_id'])
    body = c.post('/api/atlas/patch-proposals/generate', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'r10'}).json()
    assert len(body['proposal']['unified_diff_preview']) <= 12000
    assert 'diff_preview_truncated' in body['proposal']['warnings']


def test_patch_proposal_needs_revision_regeneration_policy(tmp_path):
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]
    _set_debug_review(c, pool['pool_id'], item['item_id'])
    first = c.post('/api/atlas/patch-proposals/generate', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'nr1'}).json()
    c.post('/api/atlas/patch-proposals/decide', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'proposal_id': first['proposal']['proposal_id'], 'run_id': 'nr2', 'decision': 'needs_revision'})
    second = c.post('/api/atlas/patch-proposals/generate', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'nr3'}).json()
    assert second['status'] == 'proposed'
    assert second['proposal']['proposal_id'] != first['proposal']['proposal_id']
    after = c.get(f"/api/atlas/plan-pools/{pool['pool_id']}").json()['plan_pool']
    meta = next(i for i in after['items'] if i['item_id'] == item['item_id'])['metadata']
    assert int(meta['patch_proposal_revision_count']) >= 2
