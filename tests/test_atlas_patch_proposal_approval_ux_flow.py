from pathlib import Path

from fastapi.testclient import TestClient

import main
from tests.test_atlas_patch_proposal_api import _create_pool, _set_debug_review

DASH = Path('web/js/atlas_dashboard.js').read_text(encoding='utf-8')
API = Path('app/api/atlas_pipeline.py').read_text(encoding='utf-8')


def _client(tmp_path):
    main.app.state.atlas_ca_data_dir = str(tmp_path)
    main.app.state.atlas_llm_json_fn = None
    return TestClient(main.app)


def _propose(c, pool_id, item_id, run_id='uxpp'):
    return c.post('/api/atlas/patch-proposals/generate', json={'pool_id': pool_id, 'item_id': item_id, 'run_id': run_id}).json()


def test_generated_patch_proposal_appears_as_approval_candidate_contract() -> None:
    assert 'Proposal status: ${esc(status)}' in DASH
    assert 'Approve Proposal' in DASH and 'Reject Proposal' in DASH and 'Needs Revision' in DASH
    assert 'Approval only.' in DASH
    assert 'No PlanItem draft is created automatically.' in DASH
    assert 'No patch, safe_apply, or verification rerun is executed automatically.' in DASH


def test_manual_patch_proposal_approval_preserves_source_metadata(tmp_path) -> None:
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]
    _set_debug_review(c, pool['pool_id'], item['item_id'])
    proposal = _propose(c, pool['pool_id'], item['item_id'])
    body = c.post('/api/atlas/patch-proposals/decide', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'proposal_id': proposal['proposal']['proposal_id'], 'run_id': 'ux1', 'decision': 'approved'}).json()
    assert body['status'] == 'approved'
    meta = c.get(f"/api/atlas/plan-pools/{pool['pool_id']}").json()['plan_pool']['items'][0]['metadata']['patch_proposal_approval']
    assert meta['source'] == 'patch_proposal_planitem_draft'
    assert meta['source_proposal_id']
    assert meta['manual_only'] is True
    assert meta['auto_draft_create'] is False and meta['auto_apply'] is False and meta['auto_safe_apply'] is False and meta['auto_verification'] is False


def test_manual_patch_proposal_approval_does_not_auto_create_draft_or_apply(tmp_path) -> None:
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]
    _set_debug_review(c, pool['pool_id'], item['item_id'])
    proposal = _propose(c, pool['pool_id'], item['item_id'])
    c.post('/api/atlas/patch-proposals/decide', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'proposal_id': proposal['proposal']['proposal_id'], 'run_id': 'ux2', 'decision': 'approved'})
    meta = c.get(f"/api/atlas/plan-pools/{pool['pool_id']}").json()['plan_pool']['items'][0]['metadata']
    assert 'patch_proposal_planitem_draft' not in meta
    events = '\n'.join(p.read_text(encoding='utf-8') for p in Path(tmp_path).rglob('events.ndjson'))
    for token in ('patch_proposal_planitem_draft_manual_started', 'safe_apply_manual_started', 'verification_manual_started', 'debug_review_manual_started'):
        assert token not in events


def test_no_auto_draft_safe_apply_verification_tokens() -> None:
    decide_js = DASH[DASH.index('async function decidePatchProposal'):DASH.index('async function generatePatchProposal')]
    decide_api = API[API.index('def decide_patch_proposal('):API.index('@router.post("/patch-proposals/planitem-draft"')]
    combined = decide_js + '\n' + decide_api
    for t in ('createPatchProposalPlanItemDraft(', 'executeSafeApply(', 'runVerification(', 'runDebugReview(', 'TestCommandRunner(', 'ImplementationExecutor', 'subprocess', 'shell=True', 'run_command(', 'DeepResearch'):
        assert t not in combined
