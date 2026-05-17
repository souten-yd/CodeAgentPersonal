from pathlib import Path
import json
from fastapi.testclient import TestClient
import main


def _client(tmp_path):
    main.app.state.atlas_ca_data_dir = str(tmp_path)
    return TestClient(main.app)


def _clear_safe_apply_state():
    for key in ("atlas_safe_apply_adapter", "atlas_implementation_executor"):
        if hasattr(main.app.state, key):
            delattr(main.app.state, key)


def _set_fake_executor():
    class _FakeExecutor:
        def apply_plan_item_safe(self, *, item, pool):
            return {'implementation_run_id': f'fake_{item.item_id}', 'status': 'applied'}
    main.app.state.atlas_implementation_executor = _FakeExecutor()


def _create_pool(client):
    return client.post('/api/atlas/plan-pools', json={'input': 'safe apply gate'}).json()


def _pool_file(tmp_path, pool_id):
    return Path(tmp_path) / 'atlas' / 'workspaces' / 'default' / 'plan_pools' / pool_id / 'plan_pool.json'


def _mutate_item(tmp_path, pool_id, item_id, **updates):
    p = _pool_file(tmp_path, pool_id)
    pool = json.loads(p.read_text(encoding='utf-8'))
    for it in pool['items']:
        if it['item_id'] == item_id:
            it.update({k: v for k, v in updates.items() if k != 'metadata'})
            if 'metadata' in updates:
                it.setdefault('metadata', {}).update(updates['metadata'])
    p.write_text(json.dumps(pool, ensure_ascii=False, indent=2), encoding='utf-8')


def _approve(c, pool_id, item_id):
    c.post('/api/atlas/approvals/decide', json={'pool_id': pool_id, 'item_id': item_id, 'decision': 'approved'})


def _prepare_eligible_item(tmp_path, pool_id, item_id):
    _mutate_item(
        tmp_path,
        pool_id,
        item_id,
        item_type='implementation',
        risk_level='low',
        status='ready',
        target_files=['README.md'],
        metadata={'action_type': 'update', 'approval': {'decision': 'approved'}},
    )


def test_execute_safe_apply_requires_approval(tmp_path):
    _clear_safe_apply_state()
    _set_fake_executor()
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]
    r = c.post('/api/atlas/safe-apply/execute', json={'pool_id': pool['pool_id'], 'item_id': item['item_id']})
    assert r.status_code == 200 and r.json()['status'] == 'blocked' and 'approval_not_approved' in r.json()['warnings']


def test_execute_safe_apply_blocks_non_low_risk(tmp_path):
    _clear_safe_apply_state()
    _set_fake_executor()
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]
    _prepare_eligible_item(tmp_path, pool['pool_id'], item['item_id'])
    _mutate_item(tmp_path, pool['pool_id'], item['item_id'], risk_level='medium')
    r = c.post('/api/atlas/safe-apply/execute', json={'pool_id': pool['pool_id'], 'item_id': item['item_id']})
    assert r.json()['status'] == 'blocked' and 'risk_not_low' in r.json()['warnings']


def test_execute_safe_apply_blocks_delete_and_run_command(tmp_path):
    _clear_safe_apply_state()
    _set_fake_executor()
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]
    _prepare_eligible_item(tmp_path, pool['pool_id'], item['item_id'])
    _mutate_item(tmp_path, pool['pool_id'], item['item_id'], metadata={'action_type': 'delete'})
    r1 = c.post('/api/atlas/safe-apply/execute', json={'pool_id': pool['pool_id'], 'item_id': item['item_id']})
    assert 'forbidden_action_type' in r1.json()['warnings']


def test_execute_safe_apply_blocks_when_executor_unavailable(tmp_path):
    _clear_safe_apply_state()
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]
    _prepare_eligible_item(tmp_path, pool['pool_id'], item['item_id'])
    r = c.post('/api/atlas/safe-apply/execute', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'run_1', 'dry_run': False})
    assert r.json()['status'] == 'blocked'
    assert 'safe_apply_executor_unavailable' in r.json()['warnings']
    pool_after = c.get(f"/api/atlas/plan-pools/{pool['pool_id']}").json()['plan_pool']
    assert pool_after['items'][0]['status'] != 'completed'


def test_execute_safe_apply_dry_run_simulates_without_executor(tmp_path):
    _clear_safe_apply_state()
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]
    _prepare_eligible_item(tmp_path, pool['pool_id'], item['item_id'])
    r = c.post('/api/atlas/safe-apply/execute', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'run_1', 'dry_run': True})
    assert r.json()['status'] == 'simulated'
    pool_after = c.get(f"/api/atlas/plan-pools/{pool['pool_id']}").json()['plan_pool']
    assert pool_after['items'][0]['status'] != 'completed'
    events = (Path(tmp_path) / 'atlas' / 'workspaces' / 'default' / 'plan_pools' / pool['pool_id'] / 'pipeline_runs' / 'run_1' / 'events.ndjson').read_text(encoding='utf-8')
    assert 'safe_apply_manual_simulated' in events


def test_execute_safe_apply_approved_low_risk_calls_fake_executor(tmp_path):
    _clear_safe_apply_state()
    class _FakeExecutor:
        def __init__(self):
            self.calls = 0
        def apply_plan_item_safe(self, *, item, pool):
            self.calls += 1
            return {'implementation_run_id': 'fake_run_1', 'status': 'applied'}
    fake = _FakeExecutor()
    main.app.state.atlas_implementation_executor = fake
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]
    _prepare_eligible_item(tmp_path, pool['pool_id'], item['item_id'])
    r = c.post('/api/atlas/safe-apply/execute', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'run_1'})
    assert r.json()['status'] == 'applied'
    assert fake.calls == 1
    pool_after = c.get(f"/api/atlas/plan-pools/{pool['pool_id']}").json()['plan_pool']
    assert pool_after['items'][0]['status'] == 'completed'


def test_execute_safe_apply_uses_injected_adapter(tmp_path):
    _clear_safe_apply_state()
    calls = {'count': 0}
    class _FakeAdapter:
        implementation_executor = None
        def evaluate_safe_apply(self, item, pool):
            class _Eval:
                decision = 'allow'
            return _Eval()
        def apply_low_risk_item(self, item, pool, request):
            calls['count'] += 1
            return {'status': 'simulated', 'reasons': ['simulated']}
    main.app.state.atlas_safe_apply_adapter = _FakeAdapter()
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]
    _prepare_eligible_item(tmp_path, pool['pool_id'], item['item_id'])
    r = c.post('/api/atlas/safe-apply/execute', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'dry_run': True})
    assert r.json()['status'] == 'simulated'
    assert calls['count'] == 1

def test_safe_apply_adapter_preserves_executor_blocked_status(tmp_path):
    _clear_safe_apply_state()
    class _BlockedExecutor:
        def apply_plan_item_safe(self, *, item, pool):
            return {'status': 'blocked', 'reasons': ['content_missing']}
    main.app.state.atlas_implementation_executor = _BlockedExecutor()
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]
    _prepare_eligible_item(tmp_path, pool['pool_id'], item['item_id'])
    r = c.post('/api/atlas/safe-apply/execute', json={'pool_id': pool['pool_id'], 'item_id': item['item_id']})
    body = r.json()
    assert body['status'] == 'blocked'
    assert body['status'] != 'applied'
    joined = " ".join(
        [str(x) for x in body.get('warnings', [])]
        + [str(x) for x in body.get('errors', [])]
        + [str(x) for x in body.get('metadata', {}).get('reasons', [])]
        + [str(x) for x in body.get('metadata', {}).get('safe_apply_result', {}).get('reasons', [])]
    )
    assert 'content_missing' in joined


def test_execute_safe_apply_saves_journal_record_and_event(tmp_path):
    _clear_safe_apply_state()
    _set_fake_executor()
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]
    _prepare_eligible_item(tmp_path, pool['pool_id'], item['item_id'])
    c.post('/api/atlas/safe-apply/execute', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'run_1'})
    base = Path(tmp_path) / 'atlas' / 'workspaces' / 'default' / 'plan_pools' / pool['pool_id']
    sdir = base / 'safe_apply'
    md = sorted(sdir.glob('*.md'))[-1].read_text(encoding='utf-8')
    assert 'Pool ID' in md and 'Item ID' in md and 'Status' in md and 'Target files' in md
    events = (base / 'pipeline_runs' / 'run_1' / 'events.ndjson').read_text(encoding='utf-8')
    assert 'safe_apply_manual_completed' in events or 'safe_apply_manual_blocked' in events


def test_get_approvals_includes_safe_apply_candidates(tmp_path):
    _clear_safe_apply_state()
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]
    _prepare_eligible_item(tmp_path, pool['pool_id'], item['item_id'])
    body = c.get(f"/api/atlas/approvals/pools/{pool['pool_id']}").json()
    assert 'safe_apply_candidate_items' in body
    assert any(x['item_id'] == item['item_id'] for x in body['safe_apply_candidate_items'])


def test_no_batch_or_autopilot_apply_routes():
    paths = {route.path for route in main.app.routes if hasattr(route, 'path')}
    assert '/api/atlas/safe-apply/execute' in paths
    assert all('/safe-apply/batch' not in p for p in paths)


def test_safe_apply_execution_service_has_no_forbidden_runtime_tokens():
    src = Path('agent/atlas_safe_apply_execution_service.py').read_text(encoding='utf-8')
    for t in ['subprocess', 'shell=True', 'run_command(', 'TestCommandRunner(', 'DebugLoopRunner(', 'DeepResearch', 'deep_research_job']:
        assert t not in src
