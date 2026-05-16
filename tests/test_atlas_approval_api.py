from pathlib import Path
from fastapi.testclient import TestClient
import main


def _client(tmp_path):
    main.app.state.atlas_ca_data_dir = str(tmp_path)
    return TestClient(main.app)


def _create(client):
    r=client.post('/api/atlas/plan-pools', json={'input':'approval flow'})
    return r.json()


def test_get_approvals_lists_required_items(tmp_path):
    c=_client(tmp_path); created=_create(c)
    pool=created['plan_pool']; item=pool['items'][0]; item['status']='approval_required'
    c.post('/api/atlas/plan-pools', json={'input':'x','plan_payload':{'implementation_steps':[{'step_id':'s1','title':'t','action_type':'update','target_files':['README.md']} ]},'pool_id':created['pool_id']})
    r=c.get(f"/api/atlas/approvals/pools/{created['pool_id']}")
    assert r.status_code==200
    assert 'pending_count' in r.json()


def test_decide_approval_records_approved_without_safe_apply(tmp_path):
    c=_client(tmp_path); created=_create(c)
    item=created['plan_pool']['items'][0]['item_id']
    r=c.post('/api/atlas/approvals/decide', json={'pool_id':created['pool_id'],'item_id':item,'decision':'approved'})
    assert r.status_code==200
    body=r.json()
    assert body['approval_record']['status']=='approved'
    assert body['plan_pool']['items'][0]['metadata']['approval']['decision']=='approved'


def test_approval_record_saved_to_journal(tmp_path):
    c=_client(tmp_path); created=_create(c)
    item=created['plan_pool']['items'][0]['item_id']
    body=c.post('/api/atlas/approvals/decide', json={'pool_id':created['pool_id'],'item_id':item,'decision':'rejected'}).json()
    aid=body['approval_record']['approval_id']
    base=Path(tmp_path)/'atlas'/'workspaces'/'default'/'plan_pools'/created['pool_id']/'approvals'
    assert (base/f'{aid}.json').exists()
    assert (base/f'{aid}.md').exists()
