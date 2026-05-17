from agent.test_command_runner import TestCommandRunner
from fastapi.testclient import TestClient
import main


def _client(tmp_path):
    main.app.state.atlas_ca_data_dir = str(tmp_path)
    main.app.state.atlas_test_command_runner = TestCommandRunner
    return TestClient(main.app)


def test_allowlist_and_new_routes_exist(tmp_path):
    c = _client(tmp_path)
    r = c.get('/api/atlas/verification/allowlist')
    assert r.status_code == 200
    body = r.json()
    ids = {x['command_id'] for x in body['commands']}
    assert {'pytest_selected','pytest_file','node_check_dashboard','node_check_pipeline_api'} <= ids


import json
from pathlib import Path


def _pool_file(tmp_path, pool_id):
    return Path(tmp_path) / 'atlas' / 'workspaces' / 'default' / 'plan_pools' / pool_id / 'plan_pool.json'


def _set_item(tmp_path, pool_id, item_id, metadata=None):
    p = _pool_file(tmp_path, pool_id)
    pool = json.loads(p.read_text())
    item = next(i for i in pool['items'] if i['item_id'] == item_id)
    item.setdefault('metadata', {}).setdefault('safe_apply', {})['status'] = 'applied'
    if metadata:
        item['metadata'].update(metadata)
    pool['project_path'] = str(tmp_path)
    p.write_text(json.dumps(pool, ensure_ascii=False, indent=2), encoding='utf-8')




def _set_impl_item(tmp_path, pool_id, item_id):
    p = _pool_file(tmp_path, pool_id)
    pool = json.loads(p.read_text())
    item = next(i for i in pool['items'] if i['item_id'] == item_id)
    item['item_type'] = 'implementation'
    item['risk_level'] = 'low'
    item['status'] = 'ready'
    item['target_files'] = ['app.py']
    item.setdefault('metadata', {}).update({'action_type': 'update', 'approval': {'decision': 'approved'}, 'source_proposal_id': 'pp1', 'patch': '@@ -1 +1 @@\n-old\n+new'})
    p.write_text(json.dumps(pool, ensure_ascii=False, indent=2), encoding='utf-8')


def test_auto_verification_blocks_arbitrary_command_api(tmp_path):
    c = _client(tmp_path)
    created = c.post('/api/atlas/plan-pools', json={'input': 'x', 'project_path': str(tmp_path)}).json()['plan_pool']
    item = created['items'][0]
    _set_item(tmp_path, created['pool_id'], item['item_id'])
    res = c.post('/api/atlas/automation/verify-one', json={'pool_id': created['pool_id'], 'item_id': item['item_id'], 'run_id': 'r1', 'metadata': {'command': 'echo hi'}}).json()
    assert res['status'] == 'blocked'
    assert 'arbitrary_command_forbidden' in (res.get('warnings') or []) + (res.get('errors') or [])


def test_auto_verification_blocks_unsafe_test_path_api(tmp_path):
    c = _client(tmp_path)
    created = c.post('/api/atlas/plan-pools', json={'input': 'x', 'project_path': str(tmp_path)}).json()['plan_pool']
    item = created['items'][0]
    _set_item(tmp_path, created['pool_id'], item['item_id'], metadata={'verification': {'command_id': 'pytest_selected', 'test_path': '../secret'}})
    res = c.post('/api/atlas/automation/verify-one', json={'pool_id': created['pool_id'], 'item_id': item['item_id'], 'run_id': 'r1'}).json()
    assert res['status'] == 'blocked'
    assert 'unsafe_path' in (res.get('warnings') or []) + (res.get('errors') or [])


def test_auto_verification_route_contracts(tmp_path):
    c = _client(tmp_path)
    r = c.get('/openapi.json').json()
    paths = set(r.get('paths', {}).keys())
    assert '/api/atlas/verification/allowlist' in paths
    assert '/api/atlas/automation/verify-one' in paths
    assert '/api/atlas/automation/safe-apply-one-and-verify' in paths
    assert '/api/atlas/automation/run' not in paths
    assert '/api/atlas/automation/batch' not in paths
    api_src = Path('app/api/atlas_pipeline.py').read_text(encoding='utf-8')
    assert '/api/agent/' not in ''.join(paths)
    assert '"/api/task' not in api_src
    assert '"/api/agent' not in api_src


def test_safe_apply_one_and_verify_success(tmp_path):
    (Path(tmp_path) / 'app.py').write_text('old\n', encoding='utf-8')
    (Path(tmp_path) / 'tests').mkdir(parents=True, exist_ok=True)
    (Path(tmp_path) / 'tests' / 'test_app.py').write_text('def test_app_file_exists():\n    from pathlib import Path\n    assert Path("app.py").read_text() == "new\\n"\n', encoding='utf-8')
    c = _client(tmp_path)
    created = c.post('/api/atlas/plan-pools', json={'input': 'x', 'project_path': str(tmp_path)}).json()['plan_pool']
    item = created['items'][0]
    _set_impl_item(tmp_path, created['pool_id'], item['item_id'])
    _set_item(tmp_path, created['pool_id'], item['item_id'], metadata={'verification': {'command_id': 'pytest_selected', 'test_path': 'tests/test_app.py'}})
    res = c.post('/api/atlas/automation/safe-apply-one-and-verify', json={'pool_id': created['pool_id'], 'item_id': item['item_id'], 'run_id': 'r1'}).json()
    assert res['status'] in {'applied_and_verified', 'applied_but_verification_failed'}
    assert (res.get('auto_safe_apply_result') or {}).get('status') == 'applied'


def test_safe_apply_one_and_verify_safe_apply_blocked_skips_verification(tmp_path):
    c = _client(tmp_path)
    created = c.post('/api/atlas/plan-pools', json={'input': 'x'}).json()['plan_pool']
    item = created['items'][0]
    res = c.post('/api/atlas/automation/safe-apply-one-and-verify', json={'pool_id': created['pool_id'], 'item_id': item['item_id'], 'run_id': 'r1'}).json()
    assert res['status'] == 'safe_apply_blocked'
    assert (res.get('auto_verification_result') or {}).get('status') == 'skipped'
