import json
from pathlib import Path
from fastapi.testclient import TestClient
import main


def _client(tmp_path):
    main.app.state.atlas_ca_data_dir = str(tmp_path)
    return TestClient(main.app)


def _pool_file(tmp_path, pool_id):
    return Path(tmp_path) / 'atlas' / 'workspaces' / 'default' / 'plan_pools' / pool_id / 'plan_pool.json'


def _mutate_item(tmp_path, pool_id, item_id):
    p = _pool_file(tmp_path, pool_id)
    pool = json.loads(p.read_text())
    item = next(i for i in pool['items'] if i['item_id'] == item_id)
    item['item_type'] = 'implementation'; item['risk_level'] = 'low'; item['status'] = 'ready'; item['target_files'] = ['app.py']
    item.setdefault('metadata', {}).update({'action_type': 'update', 'approval': {'decision': 'approved'}, 'patch': '@@ -1 +1 @@\n-old\n+new', 'source_proposal_id': 'pp1'})
    pool['project_path'] = str(tmp_path)
    p.write_text(json.dumps(pool, ensure_ascii=False, indent=2), encoding='utf-8')


def test_auto_safe_apply_one_allows_and_changes_file(tmp_path):
    (Path(tmp_path) / 'app.py').write_text('old\n', encoding='utf-8')
    c = _client(tmp_path)
    created = c.post('/api/atlas/plan-pools?sync=1', json={'plan_payload': {'implementation_steps': [{'step_id': 'step_001', 'title': 'Step', 'action_type': 'update', 'target_files': ['README.md']}]}, 'input': 'x', 'project_path': str(tmp_path)}).json()['plan_pool']
    item = created['items'][0]
    _mutate_item(tmp_path, created['pool_id'], item['item_id'])
    res = c.post('/api/atlas/automation/safe-apply-one', json={'pool_id': created['pool_id'], 'item_id': item['item_id'], 'preset_id': 'guarded_low_risk', 'run_id': 'run_1'}).json()
    assert res['status'] == 'applied'
    assert (Path(tmp_path) / 'app.py').read_text(encoding='utf-8') == 'new\n'
    assert res['actual_file_changed'] is True
    assert res['changed_files'] == ['app.py']
    assert (res.get('change_snapshot') or {}).get('manifest_path')


def test_auto_safe_apply_requires_project_path(tmp_path):
    c = _client(tmp_path)
    created = c.post('/api/atlas/plan-pools?sync=1', json={'plan_payload': {'implementation_steps': [{'step_id': 'step_001', 'title': 'Step', 'action_type': 'update', 'target_files': ['README.md']}]}, 'input': 'x'}).json()['plan_pool']
    item = created['items'][0]
    res = c.post('/api/atlas/automation/safe-apply-one', json={'pool_id': created['pool_id'], 'item_id': item['item_id'], 'preset_id': 'guarded_low_risk'}).json()
    assert res['status'] in {'blocked', 'skipped'}
    assert 'project_path_missing' in (res.get('errors') or []) + (res.get('warnings') or []) + (res.get('automation_decision', {}).get('reasons') or [])
