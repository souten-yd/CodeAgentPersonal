from pathlib import Path
from fastapi.testclient import TestClient
import main

from tests.test_atlas_patch_proposal_manual_ux_flow import _create_pool, _set_debug

DASH = Path('web/js/atlas_dashboard.js').read_text(encoding='utf-8')
API = Path('app/api/atlas_pipeline.py').read_text(encoding='utf-8')
APPROVAL_SERVICE = Path('agent/atlas_patch_proposal_approval_service.py').read_text(encoding='utf-8')


def _client(tmp_path):
    main.app.state.atlas_ca_data_dir = str(tmp_path)
    main.app.state.atlas_llm_json_fn = None
    return TestClient(main.app)


def _propose(c, pool_id, item_id, run_id='uxp'):
    return c.post('/api/atlas/patch-proposals/generate', json={'pool_id': pool_id, 'item_id': item_id, 'run_id': run_id}).json()


def test_generated_patch_proposal_appears_as_approval_candidate_contract():
    assert 'Proposal status:' in DASH
    assert 'Approve Proposal' in DASH and 'Reject Proposal' in DASH and 'Needs Revision' in DASH
    assert 'Approval only.' in DASH
    assert 'No PlanItem draft is created automatically.' in DASH
    assert 'No patch, safe_apply, or verification rerun is executed automatically.' in DASH


def test_manual_patch_proposal_approval_approves_generated_proposal(tmp_path):
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]
    _set_debug(c, pool['pool_id'], item['item_id'])
    p = _propose(c, pool['pool_id'], item['item_id'])
    body = c.post('/api/atlas/patch-proposals/decide', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'proposal_id': p['proposal']['proposal_id'], 'run_id': 'uxa1', 'decision': 'approved'}).json()
    assert body['status'] == 'approved'
    meta = c.get(f"/api/atlas/plan-pools/{pool['pool_id']}").json()['plan_pool']['items'][0]['metadata']
    assert meta['patch_proposal']['status'] == 'approved'
    assert meta['patch_proposal_approval']['decision'] == 'approved'


def test_manual_patch_proposal_approval_rejects_generated_proposal(tmp_path):
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]
    _set_debug(c, pool['pool_id'], item['item_id']); _propose(c, pool['pool_id'], item['item_id'])
    body = c.post('/api/atlas/patch-proposals/decide', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'uxa2', 'decision': 'rejected'}).json()
    assert body['status'] == 'rejected'
    assert c.get(f"/api/atlas/plan-pools/{pool['pool_id']}").json()['plan_pool']['items'][0]['metadata']['patch_proposal']['status'] == 'rejected'


def test_manual_patch_proposal_approval_needs_revision(tmp_path):
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]
    _set_debug(c, pool['pool_id'], item['item_id']); _propose(c, pool['pool_id'], item['item_id'])
    body = c.post('/api/atlas/patch-proposals/decide', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'uxa3', 'decision': 'needs_revision'}).json()
    assert body['status'] == 'needs_revision'
    assert c.get(f"/api/atlas/plan-pools/{pool['pool_id']}").json()['plan_pool']['items'][0]['metadata']['patch_proposal']['status'] == 'needs_revision'
    regen = _propose(c, pool['pool_id'], item['item_id'], 'uxa4')
    assert regen['status'] == 'proposed'


def test_manual_patch_proposal_approval_preserves_source_metadata(tmp_path):
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]
    _set_debug(c, pool['pool_id'], item['item_id']); _propose(c, pool['pool_id'], item['item_id'])
    c.post('/api/atlas/patch-proposals/decide', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'uxa5', 'decision': 'approved'})
    appr = c.get(f"/api/atlas/plan-pools/{pool['pool_id']}").json()['plan_pool']['items'][0]['metadata']['patch_proposal_approval']
    assert appr['source'] == 'patch_proposal_planitem_draft'
    assert appr['source_proposal_id']
    assert appr['manual_only'] is True
    assert appr['auto_draft_create'] is False and appr['auto_apply'] is False
    assert appr['auto_safe_apply'] is False and appr['auto_verification'] is False


def test_manual_patch_proposal_approval_does_not_auto_create_draft_or_apply(tmp_path):
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]
    _set_debug(c, pool['pool_id'], item['item_id']); _propose(c, pool['pool_id'], item['item_id'])
    c.post('/api/atlas/patch-proposals/decide', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'uxa6', 'decision': 'approved'})
    meta = c.get(f"/api/atlas/plan-pools/{pool['pool_id']}").json()['plan_pool']['items'][0]['metadata']
    assert 'patch_proposal_planitem_draft' not in meta
    events = '\n'.join(p.read_text(encoding='utf-8') for p in Path(tmp_path).rglob('events.ndjson'))
    for token in ('patch_proposal_planitem_draft_manual_started', 'safe_apply_manual_started', 'verification_manual_started', 'debug_review_manual_started'):
        assert token not in events


def test_patch_proposal_approval_blocked_without_proposal(tmp_path):
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]
    body = c.post('/api/atlas/patch-proposals/decide', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'uxa7', 'decision': 'approved'}).json()
    assert body['status'] == 'blocked' and 'patch_proposal_not_found' in body['warnings']


def test_patch_proposal_approval_blocks_proposal_id_mismatch(tmp_path):
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]
    _set_debug(c, pool['pool_id'], item['item_id']); _propose(c, pool['pool_id'], item['item_id'])
    body = c.post('/api/atlas/patch-proposals/decide', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'proposal_id': 'mismatch', 'run_id': 'uxa8', 'decision': 'approved'}).json()
    assert body['status'] == 'blocked' and 'proposal_id_mismatch' in body['warnings']


def test_no_patch_apply_or_batch_routes_still_absent(tmp_path):
    c = _client(tmp_path)
    assert c.post('/api/atlas/patch-proposals/decide', json={'pool_id': 'x', 'item_id': 'y', 'decision': 'approved'}).status_code in {200, 400}
    assert c.post('/api/atlas/patch-proposals/apply', json={}).status_code in {404, 405}
    assert c.post('/api/atlas/patch-proposals/batch', json={}).status_code in {404, 405}


def test_no_auto_draft_safe_apply_verification_tokens():
    d = DASH[DASH.index('async function decidePatchProposal'):DASH.index('async function generatePatchProposal')]
    a = API[API.index('def decide_patch_proposal('):API.index('def create_patch_proposal_planitem_draft(')]
    combined = d + '\n' + a + '\n' + APPROVAL_SERVICE
    for t in ('createPatchProposalPlanItemDraft(', 'executeSafeApply(', 'runVerification(', 'runDebugReview(', 'TestCommandRunner(', 'ImplementationExecutor', 'subprocess', 'shell=True', 'run_command(', 'DeepResearch'):
        assert t not in combined
