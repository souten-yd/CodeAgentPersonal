from pathlib import Path

from fastapi.testclient import TestClient
import main
from tests.test_atlas_auto_verification_api import _client,_set_impl_item,_set_item


def test_safe_apply_one_and_verify_failed_includes_failure_suggestion(tmp_path):
    (Path(tmp_path) / 'app.py').write_text('old\n', encoding='utf-8')
    (Path(tmp_path) / 'tests').mkdir(parents=True, exist_ok=True)
    (Path(tmp_path) / 'tests' / 'test_app.py').write_text('def test_app_file_exists():\n    assert False\n', encoding='utf-8')
    c = _client(tmp_path)
    created = c.post('/api/atlas/plan-pools', json={'input': 'x', 'project_path': str(tmp_path)}).json()['plan_pool']
    item = created['items'][0]
    _set_impl_item(tmp_path, created['pool_id'], item['item_id'])
    _set_item(tmp_path, created['pool_id'], item['item_id'], metadata={'verification': {'command_id': 'pytest_selected', 'test_path': 'tests/test_app.py'}})
    res = c.post('/api/atlas/automation/safe-apply-one-and-verify', json={'pool_id': created['pool_id'], 'item_id': item['item_id'], 'run_id': 'r1'}).json()
    assert res['status'] == 'applied_but_verification_failed'
    assert (res.get('failure_stop_suggestion') or {}).get('status') == 'stopped'
    assert (res.get('failure_stop_suggestion') or {}).get('snapshot_manifest_path')


def test_failure_suggestion_api_no_side_effect(tmp_path):
    c = _client(tmp_path)
    created = c.post('/api/atlas/plan-pools', json={'input': 'x'}).json()['plan_pool']
    item = created['items'][0]
    before = Path(tmp_path).rglob('*')
    res = c.post('/api/atlas/automation/failure-suggestion', json={'pool_id': created['pool_id'], 'item_id': item['item_id'], 'run_id': 'r1', 'phase': 'auto_verification', 'workspace_id': 'default'}).json()
    assert res['status'] in {'blocked','no_action','stopped'}
    text='\n'.join(str(p) for p in Path(tmp_path).rglob('events.ndjson') if p.exists())
    assert 'restore' not in text and 'debug' not in text and 'patch' not in text


def test_no_auto_rollback_routes():
    paths = {route.path for route in main.app.routes if hasattr(route, 'path')}
    assert '/api/atlas/automation/rollback' not in paths
    assert '/api/atlas/automation/restore' not in paths
    assert '/api/atlas/automation/run' not in paths
    api_source = Path('app/api/atlas_pipeline.py').read_text(encoding='utf-8')
    assert '"/api/task' not in api_source
    assert '"/api/agent' not in api_source
