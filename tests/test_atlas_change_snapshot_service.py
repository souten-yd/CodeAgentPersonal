from pathlib import Path
import json

from fastapi.testclient import TestClient
import main
from agent.atlas_change_snapshot_service import AtlasChangeSnapshotService
from agent.atlas_journal import AtlasJournal
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage


def _client(tmp_path):
    main.app.state.atlas_ca_data_dir = str(tmp_path)
    return TestClient(main.app)


def _create_pool(c):
    return c.post('/api/atlas/plan-pools?sync=1', json={'plan_payload': {'implementation_steps': [{'step_id': 'step_001', 'title': 'Step', 'action_type': 'update', 'target_files': ['README.md']}]}, 'input': 'snapshot'}).json()


def _mutate_item(tmp_path, pool_id, item_id, **updates):
    paths = [Path(tmp_path) / 'atlas' / 'workspaces' / 'default' / 'plan_pools' / pool_id / 'plan_pool.json', Path(tmp_path) / 'atlas' / 'plan_pools' / f'{pool_id}.json']
    data = json.loads(paths[0].read_text(encoding='utf-8'))
    for it in data['items']:
        if it['item_id'] == item_id:
            it.update(updates)
    for p in paths:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def _svc(tmp_path):
    return AtlasChangeSnapshotService(journal=AtlasJournal(root_dir=Path(tmp_path)), storage=AtlasPlanPoolStorage(root_dir=Path(tmp_path)))


def test_change_snapshot_saves_existing_target_file(tmp_path):
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]
    f = Path(tmp_path) / 'atlas' / 'workspaces' / 'default' / 'README.md'; f.parent.mkdir(parents=True, exist_ok=True); f.write_text('abc', encoding='utf-8')
    _mutate_item(tmp_path, pool['pool_id'], item['item_id'], target_files=['README.md'])
    r = _svc(tmp_path).create_snapshot(pool['pool_id'], item['item_id'])
    assert r.status == 'saved'
    assert Path(r.snapshot.manifest_path).exists()
    assert Path(r.snapshot.target_files[0].backup_path).exists()
    assert r.snapshot.target_files[0].sha256_before


def test_change_snapshot_records_missing_file(tmp_path):
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]
    _mutate_item(tmp_path, pool['pool_id'], item['item_id'], target_files=['missing.txt'])
    r = _svc(tmp_path).create_snapshot(pool['pool_id'], item['item_id'])
    assert r.status == 'saved'
    assert r.snapshot.target_files[0].existed_before is False
    assert r.snapshot.target_files[0].backup_path == ''


def test_change_snapshot_blocks_unsafe_paths(tmp_path):
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]
    _mutate_item(tmp_path, pool['pool_id'], item['item_id'], target_files=['../secret'])
    r = _svc(tmp_path).create_snapshot(pool['pool_id'], item['item_id'])
    assert r.status == 'blocked' and 'unsafe_target_path' in r.warnings


def test_change_snapshot_blocks_no_target_files(tmp_path):
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]
    _mutate_item(tmp_path, pool['pool_id'], item['item_id'], target_files=[])
    r = _svc(tmp_path).create_snapshot(pool['pool_id'], item['item_id'])
    assert r.status == 'blocked' and 'no_target_files' in r.warnings
