from pathlib import Path

from fastapi.testclient import TestClient

import main
from agent.atlas_patch_proposal_approval_schema import AtlasPatchProposalApprovalRequest
from tests.test_atlas_patch_proposal_api import _create_pool, _set_debug_review


def _client(tmp_path):
    main.app.state.atlas_ca_data_dir = str(tmp_path)
    main.app.state.atlas_llm_json_fn = None
    return TestClient(main.app)


def _propose(c, pool_id, item_id, run_id='rpp'):
    return c.post('/api/atlas/patch-proposals/generate', json={'pool_id': pool_id, 'item_id': item_id, 'run_id': run_id}).json()


def test_patch_proposal_approval_requires_existing_proposal(tmp_path):
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]
    body = c.post('/api/atlas/patch-proposals/decide', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'r1', 'decision': 'approved'}).json()
    assert body['status'] == 'blocked' and 'patch_proposal_not_found' in body['warnings']


def test_patch_proposal_approval_approves_proposed_proposal(tmp_path):
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]; _set_debug_review(c,pool['pool_id'],item['item_id']); p = _propose(c,pool['pool_id'],item['item_id'])
    body = c.post('/api/atlas/patch-proposals/decide', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'proposal_id': p['proposal']['proposal_id'], 'run_id': 'r2', 'decision': 'approved'}).json()
    assert body['status'] == 'approved'
    after = c.get(f"/api/atlas/plan-pools/{pool['pool_id']}").json()['plan_pool']
    meta = next(i for i in after['items'] if i['item_id']==item['item_id'])['metadata']
    assert meta['patch_proposal_approval']['decision'] == 'approved' and meta['patch_proposal']['status'] == 'approved'


def test_patch_proposal_approval_rejects_proposal(tmp_path):
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]; _set_debug_review(c,pool['pool_id'],item['item_id']); _propose(c,pool['pool_id'],item['item_id'])
    body = c.post('/api/atlas/patch-proposals/decide', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'r3', 'decision': 'rejected'}).json()
    assert body['status'] == 'rejected'


def test_patch_proposal_approval_needs_revision(tmp_path):
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]; _set_debug_review(c,pool['pool_id'],item['item_id']); _propose(c,pool['pool_id'],item['item_id'])
    body = c.post('/api/atlas/patch-proposals/decide', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'r4', 'decision': 'needs_revision'}).json()
    assert body['status'] == 'needs_revision'


def test_patch_proposal_approval_blocks_proposal_id_mismatch(tmp_path):
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]; _set_debug_review(c,pool['pool_id'],item['item_id']); _propose(c,pool['pool_id'],item['item_id'])
    body = c.post('/api/atlas/patch-proposals/decide', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'proposal_id': 'bad', 'run_id': 'r5', 'decision': 'approved'}).json()
    assert body['status'] == 'blocked' and 'proposal_id_mismatch' in body['warnings']


def test_patch_proposal_approval_record_saved_and_event(tmp_path):
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]; _set_debug_review(c,pool['pool_id'],item['item_id']); _propose(c,pool['pool_id'],item['item_id'])
    body = c.post('/api/atlas/patch-proposals/decide', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'r6', 'decision': 'approved'}).json()
    md = Path(body['metadata']['approval_md_path'])
    assert md.exists() and any(Path(tmp_path).rglob('patch_proposal_approvals/*.json'))
    events = '\n'.join(p.read_text(encoding='utf-8') for p in Path(tmp_path).rglob('events.ndjson'))
    assert 'patch_proposal_approval_manual_decided' in events
    t = md.read_text(encoding='utf-8')
    assert 'No patch was applied.' in t and 'No safe_apply was run.' in t and 'No verification rerun was performed.' in t


def test_patch_proposal_approval_response_includes_recovery_orchestration_continuation(tmp_path):
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]; _set_debug_review(c,pool['pool_id'],item['item_id']); _propose(c,pool['pool_id'],item['item_id'])
    body = c.post('/api/atlas/patch-proposals/decide', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'r7', 'decision': 'approved'}).json()
    assert body.get('recovery_summary') and body.get('orchestration_summary') and body.get('continuation_prompt')


def test_patch_proposal_approval_does_not_apply_or_verify():
    src = Path('agent/atlas_patch_proposal_approval_service.py').read_text(encoding='utf-8')
    for t in ('safe_apply(', 'execute_safe_apply', 'runVerification', 'TestCommandRunner(', 'ImplementationExecutor', 'subprocess', 'shell=True', 'run_command('):
        assert t not in src


def test_no_patch_apply_or_batch_routes_still_absent(tmp_path):
    c = _client(tmp_path)
    assert c.post('/api/atlas/patch-proposals/decide', json={'pool_id': 'x', 'item_id': 'y', 'decision': 'approved'}).status_code in {200, 400}
    assert c.post('/api/atlas/patch-proposals/apply', json={}).status_code in {404, 405}
    assert c.post('/api/atlas/patch-proposals/batch', json={}).status_code in {404, 405}


def test_patch_proposal_approval_request_has_no_patch_command_apply_fields():
    fields = set(AtlasPatchProposalApprovalRequest.model_fields.keys())
    for forbidden in ('patch', 'command', 'apply', 'shell', 'execute'):
        assert forbidden not in fields
