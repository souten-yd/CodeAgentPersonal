from pathlib import Path
import json
from fastapi.testclient import TestClient
import main


def _prepare_loop_until_candidate(tmp_path):
    main.app.state.atlas_ca_data_dir = str(tmp_path)
    c = TestClient(main.app)
    pool = c.post('/api/atlas/plan-pools', json={'input': 'x'}).json()['plan_pool']
    pool_id, item_id, run_id = pool['pool_id'], pool['items'][0]['item_id'], 'r1'

    path = Path(tmp_path) / 'atlas/workspaces/default/plan_pools' / pool_id / 'plan_pool.json'
    payload = c.get(f'/api/atlas/plan-pools/{pool_id}').json()['plan_pool']
    item = next(x for x in payload['items'] if x['item_id'] == item_id)
    item.setdefault('metadata', {})['debug_review'] = {'status': 'analyzed', 'proposed_fix': 'fix', 'source': 'verification'}
    item['target_files'] = ['agent/atlas_approval_service.py']
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

    c.post('/api/atlas/patch-proposals/generate', json={'pool_id': pool_id, 'item_id': item_id, 'run_id': run_id})
    gen_pool = c.get(f'/api/atlas/plan-pools/{pool_id}').json()['plan_pool']
    proposal_id = next(x for x in gen_pool['items'] if x['item_id'] == item_id)['metadata']['patch_proposal']['proposal_id']
    c.post('/api/atlas/patch-proposals/decide', json={'pool_id': pool_id, 'item_id': item_id, 'proposal_id': proposal_id, 'run_id': run_id, 'decision': 'approved'})
    draft = c.post('/api/atlas/patch-proposals/planitem-draft', json={'pool_id': pool_id, 'item_id': item_id, 'run_id': run_id}).json()['draft_item']['draft_item_id']
    c.post('/api/atlas/approvals/decide', json={'pool_id': pool_id, 'item_id': draft, 'run_id': run_id, 'decision': 'approved'})
    return c, pool_id, item_id, draft, run_id


def test_manual_loop_api_smoke_until_safe_apply_candidate(tmp_path):
    c, pool_id, _, draft, run_id = _prepare_loop_until_candidate(tmp_path)
    approvals = c.get(f'/api/atlas/approvals/pools/{pool_id}').json()
    assert draft in [x['item_id'] for x in approvals['safe_apply_candidate_items']]

    final_pool = c.get(f'/api/atlas/plan-pools/{pool_id}').json()['plan_pool']
    d = next(x for x in final_pool['items'] if x['item_id'] == draft)
    assert d['status'] != 'completed'
    assert str(d.get('metadata', {}).get('safe_apply', {}).get('status', '')).lower() != 'applied'

    events = (Path(tmp_path) / 'atlas/workspaces/default/plan_pools' / pool_id / f'pipeline_runs/{run_id}/events.ndjson').read_text(encoding='utf-8')
    for t in ['safe_apply_manual_started', 'verification_manual_started', 'debug_review_manual_started']:
        assert t not in events


def test_manual_loop_smoke_records_continuation_next_action(tmp_path):
    c, pool_id, _, _, _ = _prepare_loop_until_candidate(tmp_path)
    continuation = c.get(f'/api/atlas/continuation/pools/{pool_id}').json()
    next_action = continuation.get('continuation_summary', {}).get('next_action') or continuation.get('next_action')
    assert next_action == 'Run manual safe_apply from Manual safe apply candidates.'


def test_manual_loop_smoke_reload_recovery_can_restore_pool_and_candidates(tmp_path):
    c, pool_id, _, draft, _ = _prepare_loop_until_candidate(tmp_path)
    recovery = c.get('/api/atlas/recovery/latest').json()
    summary = recovery.get('recovery_summary', recovery)
    assert summary.get('pool_id') == pool_id
    assert summary.get('run_id')
    approvals = c.get(f'/api/atlas/approvals/pools/{pool_id}').json()
    candidates = approvals.get('safe_apply_candidate_items', [])
    assert any(x.get('item_id') == draft for x in candidates)


def test_manual_loop_smoke_no_auto_execution_events(tmp_path):
    c, pool_id, _, draft, run_id = _prepare_loop_until_candidate(tmp_path)
    events = (Path(tmp_path) / 'atlas/workspaces/default/plan_pools' / pool_id / f'pipeline_runs/{run_id}/events.ndjson').read_text(encoding='utf-8')
    assert 'safe_apply_manual_started' not in events
    assert 'safe_apply_manual_completed' not in events
    assert 'verification_manual_started' not in events
    assert 'debug_review_manual_started' not in events
    assert events.count('patch_proposal_manual_started') <= 1
    assert events.count('patch_proposal_planitem_draft_manual_started') <= 1
