from pathlib import Path
from fastapi.testclient import TestClient
import main
from agent.atlas_journal import AtlasJournal
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from tests.test_atlas_patch_proposal_api import _create_pool as _seed_patch_pool

DASH = Path('web/js/atlas_dashboard.js').read_text(encoding='utf-8')
API = Path('app/api/atlas_pipeline.py').read_text(encoding='utf-8')
SERVICE = Path('agent/atlas_patch_proposal_service.py').read_text(encoding='utf-8')

def _client(tmp_path):
    main.app.state.atlas_ca_data_dir = str(tmp_path)
    main.app.state.atlas_llm_json_fn = None
    return TestClient(main.app)

def _create_pool(c):
    return _seed_patch_pool(c)

def _set_debug(c, pool_id, item_id, fix='Fix assertion', source='patch_proposal_planitem_draft', root='test_failure'):
    storage = AtlasPlanPoolStorage(Path(c.app.state.atlas_ca_data_dir))
    journal = AtlasJournal(Path(c.app.state.atlas_ca_data_dir), workspace_id='default')
    pool = storage.load_pool(pool_id)
    item = pool.get_item(item_id)
    item.metadata.setdefault('debug_review', {})
    item.metadata['debug_review'] = {'status':'analyzed','proposed_fix':fix,'root_cause_category':root,'source':source,'source_proposal_id':'pp-001','reusable_lesson':'lesson'}
    item.metadata['source']='patch_proposal'
    item.metadata['source_proposal_id']='pp-001'
    storage.save_pool(pool)
    journal.save_plan_pool(pool)

def test_debug_review_analyzed_draft_appears_as_patch_proposal_candidate_contract():
    assert "review.status || '').toLowerCase() === 'analyzed'" in DASH
    assert 'Patch Proposal Draft' in DASH and 'Approval only.' in DASH
    assert 'No PlanItem draft is created automatically.' in DASH

def test_manual_patch_proposal_generates_from_debug_reviewed_draft_with_fallback(tmp_path):
    c=_client(tmp_path);pool=_create_pool(c);item=pool['plan_pool']['items'][0];_set_debug(c,pool['pool_id'],item['item_id'])
    body=c.post('/api/atlas/patch-proposals/generate',json={'pool_id':pool['pool_id'],'item_id':item['item_id'],'run_id':'m1'}).json()
    assert body['status']=='proposed' and body['proposal']['summary'] and body['proposal']['target_files'] is not None
    assert body['plan_pool']['items'][0]['metadata']['patch_proposal']['status']=='proposed'

def test_manual_patch_proposal_uses_fake_llm_but_normalizes_untrusted_fields(tmp_path):
    c=_client(tmp_path)
    c.app.state.atlas_llm_json_fn=lambda s,u:{'status':'applied','pool_id':'x','item_id':'y','risk_level':'hack','proposed_fix':'ok'}
    pool=_create_pool(c);item=pool['plan_pool']['items'][0];_set_debug(c,pool['pool_id'],item['item_id'])
    body=c.post('/api/atlas/patch-proposals/generate',json={'pool_id':pool['pool_id'],'item_id':item['item_id'],'run_id':'m2'}).json()
    assert body['proposal']['status']=='proposed' and body['proposal']['pool_id']==pool['pool_id'] and body['proposal']['item_id']==item['item_id']
    assert body['proposal']['risk_level']=='medium' and 'llm_untrusted_fields_ignored' in body['proposal']['warnings']

def test_manual_patch_proposal_preserves_draft_debug_source_metadata(tmp_path):
    c=_client(tmp_path);pool=_create_pool(c);item=pool['plan_pool']['items'][0];_set_debug(c,pool['pool_id'],item['item_id'])
    c.post('/api/atlas/patch-proposals/generate',json={'pool_id':pool['pool_id'],'item_id':item['item_id'],'run_id':'m3'})
    meta=c.get(f"/api/atlas/plan-pools/{pool['pool_id']}").json()['plan_pool']['items'][0]['metadata']['patch_proposal']
    assert meta['source']=='patch_proposal_planitem_draft' and meta['source_proposal_id']=='pp-001' and meta['debug_review_status']=='analyzed'
    assert meta['manual_only'] is True and meta['auto_apply'] is False and meta['auto_safe_apply'] is False and meta['auto_verification'] is False

def test_manual_patch_proposal_does_not_auto_approve_or_create_draft(tmp_path):
    c=_client(tmp_path);pool=_create_pool(c);item=pool['plan_pool']['items'][0];_set_debug(c,pool['pool_id'],item['item_id'])
    c.post('/api/atlas/patch-proposals/generate',json={'pool_id':pool['pool_id'],'item_id':item['item_id'],'run_id':'m4'})
    m=c.get(f"/api/atlas/plan-pools/{pool['pool_id']}").json()['plan_pool']['items'][0]['metadata']
    assert 'patch_proposal_approval' not in m and 'patch_proposal_planitem_draft' not in m

def test_patch_proposal_blocked_without_debug_review(tmp_path):
    c=_client(tmp_path);pool=_create_pool(c);item=pool['plan_pool']['items'][0]
    body=c.post('/api/atlas/patch-proposals/generate',json={'pool_id':pool['pool_id'],'item_id':item['item_id'],'run_id':'m5'}).json()
    assert body['status']=='blocked' and 'debug_review_not_analyzed' in body['warnings']

def test_patch_proposal_blocked_without_proposed_fix(tmp_path):
    c=_client(tmp_path);pool=_create_pool(c);item=pool['plan_pool']['items'][0];_set_debug(c,pool['pool_id'],item['item_id'],fix='', root='')
    body=c.post('/api/atlas/patch-proposals/generate',json={'pool_id':pool['pool_id'],'item_id':item['item_id'],'run_id':'m6'}).json()
    assert body['status']=='blocked' and 'proposed_fix_missing' in body['warnings']

def test_no_patch_apply_or_batch_routes_still_absent(tmp_path):
    c=_client(tmp_path)
    assert c.post('/api/atlas/patch-proposals/apply', json={}).status_code in {404,405}
    assert c.post('/api/atlas/patch-proposals/batch', json={}).status_code in {404,405}

def test_no_auto_apply_safe_apply_verification_tokens():
    d = DASH[DASH.index('async function generatePatchProposal'):DASH.index('async function createPatchProposalPlanItemDraft')]
    a = API[API.index('def generate_patch_proposal('):API.index('def decide_patch_proposal(')]
    combined=d+'\n'+a+'\n'+SERVICE
    for t in ('executeSafeApply(','runVerification(','TestCommandRunner(','ImplementationExecutor','subprocess','shell=True','run_command(','DeepResearch'):
        assert t not in combined
