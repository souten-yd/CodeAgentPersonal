from pathlib import Path
import json
from fastapi.testclient import TestClient

import main


def _client(tmp_path):
    main.app.state.atlas_ca_data_dir = str(tmp_path)
    return TestClient(main.app)


def _clear_verification_state():
    for key in ("atlas_test_command_runner",):
        if hasattr(main.app.state, key):
            delattr(main.app.state, key)


def _create_pool(c):
    return c.post('/api/atlas/plan-pools', json={'input': 'verification gate'}).json()


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


def test_verification_requires_safe_apply_done(tmp_path):
    _clear_verification_state()
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]
    from agent.test_command_runner import TestCommandRunner
    main.app.state.atlas_test_command_runner = TestCommandRunner()
    r = c.post('/api/atlas/verification/run', json={'pool_id': pool['pool_id'], 'item_id': item['item_id']}).json()
    assert r['status'] == 'blocked' and 'safe_apply_not_done' in r['warnings']


def test_verification_blocks_if_test_runner_unavailable(tmp_path):
    _clear_verification_state()
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]
    _mutate_item(tmp_path, pool['pool_id'], item['item_id'], status='completed', metadata={'safe_apply': {'status': 'applied'}})
    r = c.post('/api/atlas/verification/run', json={'pool_id': pool['pool_id'], 'item_id': item['item_id']}).json()
    assert r['status'] == 'blocked'
    assert 'test_runner_unavailable' in r['warnings']


def test_verification_runs_allowlisted_command_with_fake_runner(tmp_path):
    _clear_verification_state()
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]
    _mutate_item(tmp_path, pool['pool_id'], item['item_id'], status='completed', metadata={'safe_apply': {'status': 'applied'}})
    called = {'count': 0}

    class _FakeResult:
        def __init__(self, status='passed'):
            self.status = status

        def model_dump(self):
            return {'status': self.status, 'command': 'python -m py_compile app/main.py'}

    class _FakeBatch:
        def __init__(self):
            self.results = [_FakeResult('passed')]

    class _FakeRunner:
        def run_many(self, reqs, stop_on_failure=False):
            called['count'] += 1
            assert reqs
            return _FakeBatch()

    main.app.state.atlas_test_command_runner = _FakeRunner()
    r = c.post('/api/atlas/verification/run', json={'pool_id': pool['pool_id'], 'item_id': item['item_id']}).json()
    assert called['count'] == 1
    assert r['status'] == 'passed'


def test_verification_record_saved_and_event(tmp_path):
    _clear_verification_state()
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]
    _mutate_item(tmp_path, pool['pool_id'], item['item_id'], status='completed', metadata={'safe_apply': {'status': 'applied'}})
    from agent.test_command_runner import TestCommandRunner
    main.app.state.atlas_test_command_runner = TestCommandRunner()
    r = c.post('/api/atlas/verification/run', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'run_1'}).json()
    base = Path(tmp_path) / 'atlas' / 'workspaces' / 'default' / 'plan_pools' / pool['pool_id']
    assert r['status'] in {'passed', 'failed'}
    assert Path(r['metadata']['verification_record_json']).exists()
    assert Path(r['metadata']['verification_record_md']).exists()
    events = (base / 'pipeline_runs' / 'run_1' / 'events.ndjson').read_text(encoding='utf-8')
    assert ('verification_manual_passed' in events) or ('verification_manual_failed' in events)


def test_failed_verification_does_not_start_debug_loop(tmp_path):
    _clear_verification_state()
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]
    _mutate_item(tmp_path, pool['pool_id'], item['item_id'], status='completed', metadata={'safe_apply': {'status': 'applied'}})

    class _FakeResult:
        def model_dump(self):
            return {'status': 'failed', 'command': 'python -m py_compile app/main.py'}

    class _FakeBatch:
        results = [_FakeResult()]

    class _FakeRunner:
        def run_many(self, reqs, stop_on_failure=False):
            return _FakeBatch()

    main.app.state.atlas_test_command_runner = _FakeRunner()
    r = c.post('/api/atlas/verification/run', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'run_failed'}).json()
    assert r['status'] == 'failed'
    events = (Path(tmp_path) / 'atlas' / 'workspaces' / 'default' / 'plan_pools' / pool['pool_id'] / 'pipeline_runs' / 'run_failed' / 'events.ndjson').read_text(encoding='utf-8')
    assert 'verification_manual_failed' in events
    assert 'debugloop' not in events.lower()


def test_no_batch_verification_route_and_no_arbitrary_command_field():
    paths = {route.path for route in main.app.routes if hasattr(route, 'path')}
    assert '/api/atlas/verification/run' in paths
    assert all('/verification/batch' not in p for p in paths)
    src = Path('agent/atlas_verification_gate_schema.py').read_text(encoding='utf-8')
    assert 'command:' not in src


def test_no_forbidden_tokens_in_verification_service():
    src = Path('agent/atlas_verification_gate_service.py').read_text(encoding='utf-8')
    for t in ['shell=True', 'DebugLoopRunner(', 'safe_apply(', 'DeepResearch', 'run_command(']:
        assert t not in src
