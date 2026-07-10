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


def test_auto_safe_apply_accepts_verified_already_satisfied_no_op(tmp_path):
    # Reproduces an 8th layer of the same live bug chain (#2128-#2134): even after the executor
    # correctly resolves a verified no-op (file_results[].content_mode ==
    # "no_op_already_satisfied") and returns status "applied", THIS service's own
    # "actual_file_changed must be True or it's a failure" safety check -- meant to catch a
    # SILENTLY failed apply for every other kind of change -- demoted it back to "failed" with
    # errors ["actual_file_not_changed"], because zero file change looks identical to a broken
    # apply unless the verified-no-op marker is checked too.
    content = 'unchanged\n'
    (Path(tmp_path) / 'app.py').write_text(content, encoding='utf-8')
    c = _client(tmp_path)
    created = c.post('/api/atlas/plan-pools?sync=1', json={'plan_payload': {'implementation_steps': [{'step_id': 'step_001', 'title': 'Step', 'action_type': 'update', 'target_files': ['README.md']}]}, 'input': 'x', 'project_path': str(tmp_path)}).json()['plan_pool']
    item = created['items'][0]
    p = _pool_file(tmp_path, created['pool_id'])
    pool = json.loads(p.read_text())
    pool_item = next(i for i in pool['items'] if i['item_id'] == item['item_id'])
    pool_item['item_type'] = 'implementation'; pool_item['risk_level'] = 'low'; pool_item['status'] = 'ready'; pool_item['target_files'] = ['app.py']
    pool_item.setdefault('metadata', {}).update({
        'action_type': 'update', 'approval': {'decision': 'approved'}, 'source_proposal_id': 'pp1',
        'already_satisfied_no_op': True, 'patch_content_available': True,
    })
    pool['project_path'] = str(tmp_path)
    p.write_text(json.dumps(pool, ensure_ascii=False, indent=2), encoding='utf-8')

    res = c.post('/api/atlas/automation/safe-apply-one', json={'pool_id': created['pool_id'], 'item_id': item['item_id'], 'preset_id': 'guarded_low_risk', 'run_id': 'run_noop'}).json()

    assert res['status'] == 'applied'
    assert 'actual_file_not_changed' not in (res.get('errors') or [])
    assert (Path(tmp_path) / 'app.py').read_text(encoding='utf-8') == content


def test_auto_safe_apply_requires_project_path(tmp_path):
    c = _client(tmp_path)
    created = c.post('/api/atlas/plan-pools?sync=1', json={'plan_payload': {'implementation_steps': [{'step_id': 'step_001', 'title': 'Step', 'action_type': 'update', 'target_files': ['README.md']}]}, 'input': 'x'}).json()['plan_pool']
    item = created['items'][0]
    res = c.post('/api/atlas/automation/safe-apply-one', json={'pool_id': created['pool_id'], 'item_id': item['item_id'], 'preset_id': 'guarded_low_risk'}).json()
    assert res['status'] in {'blocked', 'skipped'}
    assert 'project_path_missing' in (res.get('errors') or []) + (res.get('warnings') or []) + (res.get('automation_decision', {}).get('reasons') or [])
