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


def test_approved_patch_proposal_appears_as_draft_creation_candidate_contract():
    txt = Path('web/js/atlas_dashboard.js').read_text()
    for s in ['Create manual safe_apply PlanItem Draft','Draft creation only.','No PlanItem approval is performed automatically.','No safe_apply or verification rerun is executed automatically.']:
        assert s in txt

def test_manual_planitem_draft_created_from_approved_patch_proposal(tmp_path):
    c=_client(tmp_path); pool_id,item_id=_seed(c); _set_patch(c,pool_id,item_id)
    body=c.post('/api/atlas/patch-proposals/planitem-draft',json={'pool_id':pool_id,'item_id':item_id}).json()
    assert body['status']=='created'
    assert body['draft_item']['status']=='approval_required'
    assert body['draft_item']['requires_user_confirmation'] is True

def test_manual_planitem_draft_appears_in_approval_gate(tmp_path):
    c=_client(tmp_path); pool_id,item_id=_seed(c); _set_patch(c,pool_id,item_id)
    b=c.post('/api/atlas/patch-proposals/planitem-draft',json={'pool_id':pool_id,'item_id':item_id}).json(); did=b['draft_item']['draft_item_id']
    a=c.get(f'/api/atlas/approvals/pools/{pool_id}').json()
    assert any(i['item_id']==did for i in a['approval_required_items'])
    assert not any(i['item_id']==did for i in a['safe_apply_candidate_items'])

def test_manual_planitem_draft_preserves_source_metadata(tmp_path):
    c=_client(tmp_path); pool_id,item_id=_seed(c); _set_patch(c,pool_id,item_id)
    b=c.post('/api/atlas/patch-proposals/planitem-draft',json={'pool_id':pool_id,'item_id':item_id}).json(); did=b['draft_item']['draft_item_id']
    pool=c.get(f'/api/atlas/plan-pools/{pool_id}').json()['plan_pool']
    src=next(i for i in pool['items'] if i['item_id']==item_id)['metadata']['patch_proposal_planitem_draft']
    assert src['source_proposal_id']=='p1' and src['manual_only'] is True and src['auto_planitem_approval'] is False and src['auto_safe_apply'] is False and src['auto_verification'] is False
    d=next(i for i in pool['items'] if i['item_id']==did)['metadata']
    assert d['source']=='patch_proposal' and d['source_item_id']==item_id and d['source_proposal_id']=='p1' and d['manual_safe_apply_required'] is True and d['auto_execute'] is False and d['auto_verification'] is False

def test_manual_planitem_draft_does_not_auto_approve_or_safe_apply(tmp_path):
    c=_client(tmp_path); pool_id,item_id=_seed(c); _set_patch(c,pool_id,item_id)
    c.post('/api/atlas/patch-proposals/planitem-draft',json={'pool_id':pool_id,'item_id':item_id,'run_id':'r1'})
    events=(Path(tmp_path)/'atlas/workspaces/default/plan_pools'/pool_id/'pipeline_runs/r1/events.ndjson').read_text()
    for t in ['planitem_approval_manual_decided','safe_apply_manual_started','verification_manual_started','debug_review_manual_started']:
        assert t not in events

def test_planitem_draft_blocked_for_unapproved_proposal(tmp_path):
    c=_client(tmp_path); pool_id,item_id=_seed(c); _set_patch(c,pool_id,item_id,status='proposed')
    b=c.post('/api/atlas/patch-proposals/planitem-draft',json={'pool_id':pool_id,'item_id':item_id}).json()
    assert b['status']=='blocked' and any(w in b['warnings'] for w in ['patch_proposal_not_approved','patch_proposal_approval_not_approved'])

def test_planitem_draft_blocked_for_rejected_or_needs_revision(tmp_path):
    c=_client(tmp_path); pool_id,item_id=_seed(c); _set_patch(c,pool_id,item_id,status='rejected',decision='rejected')
    assert c.post('/api/atlas/patch-proposals/planitem-draft',json={'pool_id':pool_id,'item_id':item_id}).json()['status']=='blocked'

def test_planitem_draft_duplicate_blocked(tmp_path):
    c=_client(tmp_path); pool_id,item_id=_seed(c); _set_patch(c,pool_id,item_id)
    c.post('/api/atlas/patch-proposals/planitem-draft',json={'pool_id':pool_id,'item_id':item_id})
    b=c.post('/api/atlas/patch-proposals/planitem-draft',json={'pool_id':pool_id,'item_id':item_id}).json()
    assert b['status']=='blocked' and any(w in b['warnings'] for w in ['draft_already_exists','patch_proposal_planitem_draft_already_exists'])

def test_no_patch_apply_or_batch_routes_still_absent():
    src=Path('app/api/atlas_pipeline.py').read_text()
    assert '/api/atlas/patch-proposals/planitem-draft' not in src or '/patch-proposals/planitem-draft' in src
    for t in ['/patch-proposals/apply','/patch-proposals/batch','/patch-proposals/planitem-draft/batch']:
        assert t not in src

def test_no_auto_approval_safe_apply_verification_tokens():
    ui=Path('web/js/atlas_dashboard.js').read_text(); api=Path('app/api/atlas_pipeline.py').read_text(); svc=Path('agent/atlas_patch_proposal_planitem_service.py').read_text()
    snippet=ui[ui.index('async function createPatchProposalPlanItemDraft'):ui.index('function renderPatchProposalPanel')]
    route=api[api.index('def create_patch_proposal_planitem_draft'):api.index('@router.get("/recovery/latest"')]
    for t in ['decideApproval(','executeSafeApply(','runVerification(','runDebugReview(','TestCommandRunner(','ImplementationExecutor','subprocess','shell=True','run_command(','DeepResearch']:
        assert t not in snippet
        assert t not in route
        assert t not in svc
