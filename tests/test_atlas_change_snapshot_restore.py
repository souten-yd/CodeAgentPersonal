from pathlib import Path
import json

from fastapi.testclient import TestClient
import main
from agent.atlas_change_snapshot_service import AtlasChangeSnapshotService
from agent.atlas_change_snapshot_restore_schema import AtlasChangeSnapshotRestoreRequest
from agent.atlas_change_snapshot_restore_service import AtlasChangeSnapshotRestoreService
from agent.atlas_journal import AtlasJournal
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage


def _client(tmp_path):
    main.app.state.atlas_ca_data_dir = str(tmp_path)
    return TestClient(main.app)


def _create_pool(c):
    return c.post('/api/atlas/plan-pools?sync=1', json={'input': 'snapshot restore'}).json()


def _mutate_item(tmp_path, pool_id, item_id, **updates):
    paths = [Path(tmp_path) / 'atlas' / 'workspaces' / 'default' / 'plan_pools' / pool_id / 'plan_pool.json', Path(tmp_path) / 'atlas' / 'plan_pools' / f'{pool_id}.json']
    data = json.loads(paths[0].read_text(encoding='utf-8'))
    for it in data['items']:
        if it['item_id'] == item_id:
            it.update(updates)
    for p in paths:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def _snapshot_and_manifest(tmp_path, pool_id, item_id):
    snap = AtlasChangeSnapshotService(journal=AtlasJournal(root_dir=Path(tmp_path)), storage=AtlasPlanPoolStorage(root_dir=Path(tmp_path))).create_snapshot(pool_id, item_id)
    assert snap.snapshot is not None
    return snap.snapshot.manifest_path


def test_restore_modified_file_from_snapshot(tmp_path):
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]
    f = Path(tmp_path) / 'atlas' / 'workspaces' / 'default' / 'README.md'; f.parent.mkdir(parents=True, exist_ok=True); f.write_text('before', encoding='utf-8')
    _mutate_item(tmp_path, pool['pool_id'], item['item_id'], target_files=['README.md'])
    manifest = _snapshot_and_manifest(tmp_path, pool['pool_id'], item['item_id'])
    f.write_text('after', encoding='utf-8')
    svc = AtlasChangeSnapshotRestoreService(journal=AtlasJournal(root_dir=Path(tmp_path)))
    r = svc.restore(AtlasChangeSnapshotRestoreRequest(pool_id=pool['pool_id'], item_id=item['item_id'], manifest_path=manifest))
    assert r.status == 'restored'
    assert f.read_text(encoding='utf-8') == 'before'


def test_restore_missing_before_file_is_safe_by_default(tmp_path):
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]
    target = Path(tmp_path) / 'atlas' / 'workspaces' / 'default' / 'new_file.txt'
    _mutate_item(tmp_path, pool['pool_id'], item['item_id'], target_files=['new_file.txt'])
    manifest = _snapshot_and_manifest(tmp_path, pool['pool_id'], item['item_id'])
    target.write_text('created later', encoding='utf-8')
    svc = AtlasChangeSnapshotRestoreService(journal=AtlasJournal(root_dir=Path(tmp_path)))
    r = svc.restore(AtlasChangeSnapshotRestoreRequest(pool_id=pool['pool_id'], item_id=item['item_id'], manifest_path=manifest))
    assert r.file_results[0].skipped is True
    assert r.file_results[0].skip_reason == 'manual_confirm_required_for_delete'
    assert target.exists()


def test_restore_blocks_unsafe_path(tmp_path):
    svc = AtlasChangeSnapshotRestoreService(journal=AtlasJournal(root_dir=Path(tmp_path)))
    manifest = Path(tmp_path) / 'manifest.json'
    manifest.write_text(json.dumps({'target_files': [{'path': '../secret', 'existed_before': True, 'backup_path': ''}]}), encoding='utf-8')
    r = svc.restore(AtlasChangeSnapshotRestoreRequest(pool_id='p1', item_id='i1', run_id='run_1', manifest_path=str(manifest)))
    assert r.status == 'blocked' and 'unsafe_target_path' in r.warnings


def test_restore_api_and_ui_manual_only_contract():
    api = Path('web/js/atlas_pipeline_api.js').read_text(encoding='utf-8')
    ui = Path('web/js/atlas_dashboard.js').read_text(encoding='utf-8')
    assert 'restoreChangeSnapshot(payload)' in api
    assert '/api/atlas/change-snapshots/restore' in api
    assert 'Restore from Snapshot' in ui
    assert 'Restore is manual only' in ui
    assert 'Auto rollback is not enabled' in ui
    assert 'runVerification(' not in ui[ui.index('async function restoreFromSnapshot'):ui.index('async function decideApproval')]
