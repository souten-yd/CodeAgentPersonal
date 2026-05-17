from pathlib import Path
from fastapi.testclient import TestClient
import main


def _client(tmp_path):
    main.app.state.atlas_ca_data_dir = str(tmp_path)
    return TestClient(main.app)


def _seed(c):
    pool = c.post('/api/atlas/plan-pools', json={'input':'x'}).json()['plan_pool']
    return pool['pool_id'], pool['items'][0]['item_id']


def _set_patch(c,pool_id,item_id,status='approved',decision='approved'):
    pool = c.get(f'/api/atlas/plan-pools/{pool_id}').json()['plan_pool']
    item = next(i for i in pool['items'] if i['item_id']==item_id)
    item.setdefault('metadata',{})['patch_proposal']={'status':status,'proposal_id':'p1','summary':'s','risk_level':'low','target_files':['agent/x.py'],'suggested_changes':[{'a':1}]}
    item['metadata']['patch_proposal_approval']={'decision':decision}
    p = Path(main.app.state.atlas_ca_data_dir)/'atlas/workspaces/default/plan_pools'/pool_id/'plan_pool.json'
    import json; p.write_text(json.dumps(pool,ensure_ascii=False,indent=2),encoding='utf-8')


def _create_draft(c,pool_id,item_id):
    _set_patch(c,pool_id,item_id)
    body=c.post('/api/atlas/patch-proposals/planitem-draft',json={'pool_id':pool_id,'item_id':item_id,'run_id':'r1'}).json()
    return body['draft_item']['draft_item_id']


def test_created_planitem_draft_appears_as_approval_candidate_contract():
    txt = Path('web/js/atlas_dashboard.js').read_text(encoding='utf-8')
    for s in ['Patch Proposal Draft','PlanItem approval only.','No safe_apply is executed automatically.','No verification or DebugReview is executed automatically.']:
        assert s in txt


def test_manual_planitem_approval_approves_generated_draft(tmp_path):
    c=_client(tmp_path); pool_id,item_id=_seed(c); did=_create_draft(c,pool_id,item_id)
    body=c.post('/api/atlas/approvals/decide',json={'pool_id':pool_id,'item_id':did,'run_id':'r1','decision':'approved'}).json()
    assert body['decision']=='approved'
    pool=c.get(f'/api/atlas/plan-pools/{pool_id}').json()['plan_pool']
    d=next(i for i in pool['items'] if i['item_id']==did)
    assert d['metadata']['approval']['decision']=='approved'


def test_approved_draft_becomes_manual_safe_apply_candidate(tmp_path):
    c=_client(tmp_path); pool_id,item_id=_seed(c); did=_create_draft(c,pool_id,item_id)
    c.post('/api/atlas/approvals/decide',json={'pool_id':pool_id,'item_id':did,'run_id':'r1','decision':'approved'})
    a=c.get(f'/api/atlas/approvals/pools/{pool_id}').json()
    assert did in [i['item_id'] for i in a['safe_apply_candidate_items']]


def test_manual_planitem_approval_rejects_generated_draft(tmp_path):
    c=_client(tmp_path); pool_id,item_id=_seed(c); did=_create_draft(c,pool_id,item_id)
    c.post('/api/atlas/approvals/decide',json={'pool_id':pool_id,'item_id':did,'run_id':'r1','decision':'rejected'})
    pool=c.get(f'/api/atlas/plan-pools/{pool_id}').json()['plan_pool']
    d=next(i for i in pool['items'] if i['item_id']==did)
    assert d['metadata']['approval']['decision']=='rejected'
    a=c.get(f'/api/atlas/approvals/pools/{pool_id}').json()
    assert did not in [i['item_id'] for i in a['safe_apply_candidate_items']]


def test_manual_planitem_approval_needs_revision_generated_draft(tmp_path):
    c=_client(tmp_path); pool_id,item_id=_seed(c); did=_create_draft(c,pool_id,item_id)
    c.post('/api/atlas/approvals/decide',json={'pool_id':pool_id,'item_id':did,'run_id':'r1','decision':'needs_revision'})
    pool=c.get(f'/api/atlas/plan-pools/{pool_id}').json()['plan_pool']
    d=next(i for i in pool['items'] if i['item_id']==did)
    assert d['metadata']['approval']['decision']=='needs_revision'


def test_manual_planitem_approval_preserves_source_metadata(tmp_path):
    c=_client(tmp_path); pool_id,item_id=_seed(c); did=_create_draft(c,pool_id,item_id)
    c.post('/api/atlas/approvals/decide',json={'pool_id':pool_id,'item_id':did,'run_id':'r1','decision':'approved'})
    pool=c.get(f'/api/atlas/plan-pools/{pool_id}').json()['plan_pool']
    ap=next(i for i in pool['items'] if i['item_id']==did)['metadata']['approval']
    assert ap['source']=='patch_proposal_planitem_draft' and ap['source_item_id'] and ap['source_proposal_id']=='p1'
    assert ap['manual_only'] is True and ap['auto_safe_apply'] is False and ap['auto_verification'] is False and ap['auto_debug_review'] is False


def test_manual_planitem_approval_does_not_auto_safe_apply_or_verify(tmp_path):
    c=_client(tmp_path); pool_id,item_id=_seed(c); did=_create_draft(c,pool_id,item_id)
    c.post('/api/atlas/approvals/decide',json={'pool_id':pool_id,'item_id':did,'run_id':'r1','decision':'approved'})
    events=(Path(tmp_path)/'atlas/workspaces/default/plan_pools'/pool_id/'pipeline_runs/r1/events.ndjson').read_text(encoding='utf-8')
    for t in ['safe_apply_manual_started','safe_apply_manual_completed','verification_manual_started','debug_review_manual_started','patch_proposal_manual_started']:
        assert t not in events


def test_no_batch_or_auto_approval_routes():
    src=Path('app/api/atlas_pipeline.py').read_text(encoding='utf-8')
    assert '/approvals/decide' in src
    assert '/api/atlas/approvals/batch' not in src
    assert '/api/atlas/safe-apply/batch' not in src


def test_no_auto_safe_apply_verification_debug_tokens():
    ui=Path('web/js/atlas_dashboard.js').read_text(encoding='utf-8')
    api=Path('app/api/atlas_pipeline.py').read_text(encoding='utf-8')
    snippet=ui[ui.index('async function decideApproval'):ui.index('async function loadRecoveryLatest')]
    route=api[api.index('def decide_approval'):api.index('@router.get("/continuation/latest"')]
    for t in ['executeSafeApply(','runVerification(','runDebugReview(','generatePatchProposal(','TestCommandRunner(','ImplementationExecutor','subprocess','shell=True','run_command(','DeepResearch']:
        assert t not in snippet
        assert t not in route
