from pathlib import Path
from fastapi.testclient import TestClient
import main


def test_manual_loop_api_smoke_until_safe_apply_candidate(tmp_path):
    main.app.state.atlas_ca_data_dir = str(tmp_path)
    c = TestClient(main.app)
    pool = c.post('/api/atlas/plan-pools', json={'input':'x'}).json()['plan_pool']
    pool_id, item_id = pool['pool_id'], pool['items'][0]['item_id']

    p = Path(tmp_path)/'atlas/workspaces/default/plan_pools'/pool_id/'plan_pool.json'
    import json
    payload = c.get(f'/api/atlas/plan-pools/{pool_id}').json()['plan_pool']
    i = next(x for x in payload['items'] if x['item_id'] == item_id)
    i.setdefault('metadata', {})['debug_review'] = {'status': 'analyzed', 'proposed_fix': 'fix', 'source': 'verification'}
    i['target_files'] = ['agent/atlas_approval_service.py']
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

    c.post('/api/atlas/patch-proposals/generate', json={'pool_id':pool_id,'item_id':item_id,'run_id':'r1'})
    gen_pool = c.get(f'/api/atlas/plan-pools/{pool_id}').json()['plan_pool']
    proposal_id = next(x for x in gen_pool['items'] if x['item_id'] == item_id)['metadata']['patch_proposal']['proposal_id']
    c.post('/api/atlas/patch-proposals/decide', json={'pool_id':pool_id,'item_id':item_id,'proposal_id':proposal_id,'run_id':'r1','decision':'approved'})
    draft = c.post('/api/atlas/patch-proposals/planitem-draft', json={'pool_id':pool_id,'item_id':item_id,'run_id':'r1'}).json()['draft_item']['draft_item_id']
    c.post('/api/atlas/approvals/decide', json={'pool_id':pool_id,'item_id':draft,'run_id':'r1','decision':'approved'})

    approvals = c.get(f'/api/atlas/approvals/pools/{pool_id}').json()
    assert draft in [x['item_id'] for x in approvals['safe_apply_candidate_items']]

    final_pool = c.get(f'/api/atlas/plan-pools/{pool_id}').json()['plan_pool']
    d = next(x for x in final_pool['items'] if x['item_id'] == draft)
    assert d['status'] != 'completed'
    assert str(d.get('metadata', {}).get('safe_apply', {}).get('status', '')).lower() != 'applied'

    events = (Path(tmp_path)/'atlas/workspaces/default/plan_pools'/pool_id/'pipeline_runs/r1/events.ndjson').read_text(encoding='utf-8')
    for t in ['safe_apply_manual_started','verification_manual_started','debug_review_manual_started']:
        assert t not in events
