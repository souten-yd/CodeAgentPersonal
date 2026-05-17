from pathlib import Path
import main
from fastapi.testclient import TestClient
from tests.test_atlas_safe_apply_execution_api import _create_pool, _prepare_eligible_item, _clear_safe_apply_state


def _client(tmp_path):
    main.app.state.atlas_ca_data_dir = str(tmp_path)
    return TestClient(main.app)


def test_safe_apply_creates_snapshot_before_executor(tmp_path):
    _clear_safe_apply_state()
    class _FakeExecutor:
        def apply_plan_item_safe(self, *, item, pool):
            snaps = list((Path(tmp_path) / 'atlas' / 'workspaces' / 'default' / 'plan_pools' / pool.pool_id / 'change_snapshots').glob('*/*manifest.json'))
            assert snaps
            return {'status': 'applied'}
    main.app.state.atlas_implementation_executor = _FakeExecutor()
    c=_client(tmp_path); pool=_create_pool(c); item=pool['plan_pool']['items'][0]
    _prepare_eligible_item(tmp_path, pool['pool_id'], item['item_id'])
    r=c.post('/api/atlas/safe-apply/execute', json={'pool_id': pool['pool_id'], 'item_id': item['item_id']}).json()
    assert r['status']=='applied'
    assert r['metadata']['change_snapshot']['snapshot_id']


def test_safe_apply_blocks_when_snapshot_fails(tmp_path):
    _clear_safe_apply_state()
    calls={'n':0}
    class _FakeExecutor:
        def apply_plan_item_safe(self, *, item, pool):
            calls['n'] += 1
            return {'status':'applied'}
    main.app.state.atlas_implementation_executor = _FakeExecutor()
    c=_client(tmp_path); pool=_create_pool(c); item=pool['plan_pool']['items'][0]
    _prepare_eligible_item(tmp_path, pool['pool_id'], item['item_id'])
    from tests.test_atlas_safe_apply_execution_api import _mutate_item
    _mutate_item(tmp_path, pool['pool_id'], item['item_id'], target_files=['../bad'])
    r=c.post('/api/atlas/safe-apply/execute', json={'pool_id': pool['pool_id'], 'item_id': item['item_id']}).json()
    assert r['status']=='blocked'
    assert calls['n']==0
