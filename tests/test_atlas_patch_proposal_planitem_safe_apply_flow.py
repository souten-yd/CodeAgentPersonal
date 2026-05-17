from pathlib import Path
import json

from fastapi.testclient import TestClient

import main


API = Path('app/api/atlas_pipeline.py').read_text(encoding='utf-8')
DASH = Path('web/js/atlas_dashboard.js').read_text(encoding='utf-8')


def _client(tmp_path):
    main.app.state.atlas_ca_data_dir = str(tmp_path)
    return TestClient(main.app)


def _seed(c):
    pool = c.post('/api/atlas/plan-pools', json={'input': 'x'}).json()['plan_pool']
    return pool['pool_id'], pool['items'][0]['item_id']


def _set_patch(tmp_path, c, pool_id, item_id):
    pool = c.get(f'/api/atlas/plan-pools/{pool_id}').json()['plan_pool']
    it = next(x for x in pool['items'] if x['item_id'] == item_id)
    it.setdefault('metadata', {})['patch_proposal'] = {
        'status': 'approved', 'proposal_id': 'p1', 'summary': 's', 'proposed_fix': 'f', 'risk_level': 'low',
        'target_files': ['agent/x.py'], 'suggested_changes': [{'a': 1}], 'verification_plan': ['v'], 'rollback_plan': ['r'],
    }
    it['metadata']['patch_proposal_approval'] = {'decision': 'approved'}
    p = Path(tmp_path) / 'atlas' / 'workspaces' / 'default' / 'plan_pools' / pool_id / 'plan_pool.json'
    p.write_text(json.dumps(pool, ensure_ascii=False, indent=2), encoding='utf-8')


def _make_draft(c, pool_id, item_id):
    return c.post('/api/atlas/patch-proposals/planitem-draft', json={'pool_id': pool_id, 'item_id': item_id}).json()['draft_item']['draft_item_id']


def _approve(c, pool_id, item_id):
    c.post('/api/atlas/approvals/decide', json={'pool_id': pool_id, 'item_id': item_id, 'decision': 'approved'})


def test_approved_draft_manual_safe_apply_with_fake_executor_applies(tmp_path):
    class _FakeExecutor:
        def __init__(self): self.calls = 0
        def apply_plan_item_safe(self, *, item, pool): self.calls += 1; return {'status': 'applied'}
    fake = _FakeExecutor(); main.app.state.atlas_implementation_executor = fake
    c = _client(tmp_path); pool_id, item_id = _seed(c); _set_patch(tmp_path, c, pool_id, item_id)
    draft_id = _make_draft(c, pool_id, item_id); _approve(c, pool_id, draft_id)
    res = c.post('/api/atlas/safe-apply/execute', json={'pool_id': pool_id, 'item_id': draft_id, 'run_id': 'r1'}).json()
    assert res['status'] == 'applied' and fake.calls == 1
    draft = next(i for i in res['plan_pool']['items'] if i['item_id'] == draft_id)
    assert draft['status'] in {'completed', 'applied'}
    assert draft['metadata']['safe_apply']['status'] == 'applied'


def test_unapproved_draft_safe_apply_is_blocked(tmp_path):
    c = _client(tmp_path); pool_id, item_id = _seed(c); _set_patch(tmp_path, c, pool_id, item_id)
    draft_id = _make_draft(c, pool_id, item_id)
    res = c.post('/api/atlas/safe-apply/execute', json={'pool_id': pool_id, 'item_id': draft_id, 'run_id': 'r2'}).json()
    assert res['status'] == 'blocked' and 'approval_not_approved' in res['warnings']


def test_draft_safe_apply_does_not_auto_run_verification_or_debug(tmp_path):
    class _FakeExecutor:
        def apply_plan_item_safe(self, *, item, pool): return {'status': 'applied'}
    main.app.state.atlas_implementation_executor = _FakeExecutor()
    c = _client(tmp_path); pool_id, item_id = _seed(c); _set_patch(tmp_path, c, pool_id, item_id)
    draft_id = _make_draft(c, pool_id, item_id); _approve(c, pool_id, draft_id)
    res = c.post('/api/atlas/safe-apply/execute', json={'pool_id': pool_id, 'item_id': draft_id, 'run_id': 'r3'}).json()
    events = (Path(tmp_path) / 'atlas' / 'workspaces' / 'default' / 'plan_pools' / pool_id / 'pipeline_runs' / 'r3' / 'events.ndjson').read_text(encoding='utf-8')
    for token in ('verification_manual_started', 'debug_review_manual_started', 'patch_proposal_manual_started'):
        assert token not in events
    assert isinstance(res.get('continuation_prompt', ''), str)


def test_draft_safe_apply_preserves_patch_proposal_source_metadata(tmp_path):
    class _FakeExecutor:
        def apply_plan_item_safe(self, *, item, pool): return {'status': 'applied'}
    main.app.state.atlas_implementation_executor = _FakeExecutor()
    c = _client(tmp_path); pool_id, item_id = _seed(c); _set_patch(tmp_path, c, pool_id, item_id)
    draft_id = _make_draft(c, pool_id, item_id); _approve(c, pool_id, draft_id)
    res = c.post('/api/atlas/safe-apply/execute', json={'pool_id': pool_id, 'item_id': draft_id}).json()
    draft = next(i for i in res['plan_pool']['items'] if i['item_id'] == draft_id)
    safe = draft['metadata']['safe_apply']
    assert safe['source_item_id'] and safe['source_proposal_id']
    assert safe['source'] in {'patch_proposal', 'patch_proposal_planitem_draft'}


def test_no_batch_or_new_safe_apply_routes():
    assert '/safe-apply/execute' in API
    assert '/api/atlas/safe-apply/batch' not in API
    assert '/api/atlas/patch-proposals/apply' not in API


def test_ui_copy_mentions_patch_proposal_draft_manual_only():
    assert 'Patch Proposal Draft' in DASH
    assert 'Manual safe_apply only. Verification and DebugLoop are not run automatically.' in DASH


def test_no_auto_execution_tokens():
    for f in [
        'agent/atlas_safe_apply_execution_service.py',
        'agent/atlas_patch_proposal_planitem_service.py',
        'app/api/atlas_pipeline.py',
    ]:
        txt = Path(f).read_text(encoding='utf-8')
        for token in ['runVerification', 'TestCommandRunner(', 'DebugLoopRunner(', 'DeepResearch', 'subprocess', 'shell=True', 'run_command(']:
            assert token not in txt
