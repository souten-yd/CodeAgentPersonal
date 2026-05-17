from pathlib import Path
from fastapi.testclient import TestClient
import main
from agent.atlas_file_safe_apply_executor import AtlasFileSafeApplyExecutor
from tests.test_atlas_safe_apply_execution_api import _clear_safe_apply_state, _create_pool, _mutate_item


def _client(tmp_path):
    main.app.state.atlas_ca_data_dir = str(tmp_path)
    return TestClient(main.app)


def _prepare_item(tmp_path, pool_id, item_id, action_type, target, content):
    _mutate_item(tmp_path, pool_id, item_id, item_type='implementation', risk_level='low', status='ready', target_files=[target], metadata={'action_type': action_type, 'approval': {'decision': 'approved'}, 'proposed_content': content})


def test_safe_apply_update_then_restore_same_workspace_file(tmp_path):
    _clear_safe_apply_state(); c=_client(tmp_path)
    repo=tmp_path/'repo'; repo.mkdir(); (repo/'sample.txt').write_text('before\n', encoding='utf-8')
    main.app.state.atlas_implementation_executor = AtlasFileSafeApplyExecutor(workspace_root=repo)
    pool=_create_pool(c); pid=pool['pool_id']; iid=pool['plan_pool']['items'][0]['item_id']
    p=Path(tmp_path)/'atlas'/'workspaces'/'default'/'plan_pools'/pid/'plan_pool.json'
    d=__import__('json').loads(p.read_text()); d['project_path']=str(repo); p.write_text(__import__('json').dumps(d, ensure_ascii=False, indent=2))
    _prepare_item(tmp_path,pid,iid,'update','sample.txt','after\n')
    r=c.post('/api/atlas/safe-apply/execute',json={'pool_id':pid,'item_id':iid}).json(); assert r['status']=='applied'
    assert (repo/'sample.txt').read_text()=='after\n'
    manifest=r['metadata']['change_snapshot']['manifest_path']; assert Path(manifest).exists()
    rr=c.post('/api/atlas/change-snapshots/restore',json={'pool_id':pid,'item_id':iid,'manifest_path':manifest,'confirm_delete_missing_before':False}).json()
    assert rr['status']=='restored'; assert (repo/'sample.txt').read_text()=='before\n'


def test_safe_apply_snapshot_and_executor_use_same_workspace_root(tmp_path):
    _clear_safe_apply_state(); c=_client(tmp_path)
    repo=tmp_path/'repo'; repo.mkdir(); (repo/'a.txt').write_text('a\n')
    main.app.state.atlas_implementation_executor = AtlasFileSafeApplyExecutor(workspace_root=repo)
    pool=_create_pool(c); pid=pool['pool_id']; iid=pool['plan_pool']['items'][0]['item_id']
    p=Path(tmp_path)/'atlas'/'workspaces'/'default'/'plan_pools'/pid/'plan_pool.json'; import json; d=json.loads(p.read_text()); d['project_path']=str(repo); p.write_text(json.dumps(d, ensure_ascii=False, indent=2))
    _prepare_item(tmp_path,pid,iid,'update','a.txt','b\n')
    r=c.post('/api/atlas/safe-apply/execute',json={'pool_id':pid,'item_id':iid}).json(); m=r['metadata']
    assert m['workspace_root']==m['change_snapshot']['workspace_root']
