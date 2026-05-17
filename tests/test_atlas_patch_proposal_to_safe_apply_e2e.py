from pathlib import Path
from fastapi.testclient import TestClient
import main
from agent.atlas_file_safe_apply_executor import AtlasFileSafeApplyExecutor
from tests.test_atlas_safe_apply_execution_api import _clear_safe_apply_state, _create_pool

def _client(tmp_path):
    main.app.state.atlas_ca_data_dir = str(tmp_path)
    return TestClient(main.app)

def _set_project_path(tmp_path, pool_id, repo):
    p = Path(tmp_path) / 'atlas' / 'workspaces' / 'default' / 'plan_pools' / pool_id / 'plan_pool.json'
    import json
    d = json.loads(p.read_text(encoding='utf-8')); d['project_path'] = str(repo)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding='utf-8')

def _seed_patch_source(c, pool_id, item_id, patch_proposal):
    pool = c.get(f'/api/atlas/plan-pools/{pool_id}').json()['plan_pool']
    item = next(i for i in pool['items'] if i['item_id'] == item_id)
    item.setdefault('metadata', {})['patch_proposal'] = patch_proposal
    item['metadata']['patch_proposal_approval'] = {'decision': 'approved'}
    p = Path(main.app.state.atlas_ca_data_dir) / 'atlas' / 'workspaces' / 'default' / 'plan_pools' / pool_id / 'plan_pool.json'
    import json
    p.write_text(json.dumps(pool, ensure_ascii=False, indent=2), encoding='utf-8')

def _create_and_approve_draft(c, pool_id, item_id, proposal_id='pp1'):
    create = c.post('/api/atlas/patch-proposals/planitem-draft', json={'pool_id': pool_id, 'item_id': item_id, 'proposal_id': proposal_id}).json()
    assert create['status'] == 'created'
    draft_id = create['draft_item']['draft_item_id']
    approve = c.post('/api/atlas/approvals/decide', json={'pool_id': pool_id, 'item_id': draft_id, 'decision': 'approved'}).json()
    assert approve['status'] in {'approved', 'ready'}
    return create, draft_id

def test_patch_proposal_draft_safe_apply_updates_file_from_unified_diff(tmp_path):
    _clear_safe_apply_state(); c = _client(tmp_path)
    repo = tmp_path / 'repo'; repo.mkdir(); (repo / 'app.py').write_text('print("old")\n', encoding='utf-8')
    main.app.state.atlas_implementation_executor = AtlasFileSafeApplyExecutor(workspace_root=repo)
    pool = _create_pool(c); pid = pool['pool_id']; iid = pool['plan_pool']['items'][0]['item_id']
    _set_project_path(tmp_path, pid, repo)
    _seed_patch_source(c, pid, iid, {'status':'approved','proposal_id':'pp1','risk_level':'low','target_files':['app.py'],'unified_diff_preview':'--- a/app.py\n+++ b/app.py\n@@\n-print("old")\n+print("new")\n'})
    draft_body, draft_id = _create_and_approve_draft(c, pid, iid)
    md = draft_body['draft_item']['metadata']; assert md.get('patch') or md.get('proposed_content')
    assert (repo / 'app.py').read_text(encoding='utf-8') == 'print("old")\n'
    r = c.post('/api/atlas/safe-apply/execute', json={'pool_id': pid, 'item_id': draft_id}).json()
    assert r['status'] == 'applied'
    assert (repo / 'app.py').read_text(encoding='utf-8') == 'print("new")\n'
    assert r['metadata']['executor_result']['changed_files'] == ['app.py']
    assert r['metadata']['executor_result']['actual_file_changed'] is True
    assert Path(r['metadata']['change_snapshot']['manifest_path']).exists()

def test_patch_proposal_draft_safe_apply_restore_returns_file(tmp_path):
    _clear_safe_apply_state(); c = _client(tmp_path)
    repo = tmp_path / 'repo'; repo.mkdir(); (repo / 'app.py').write_text('print("old")\n', encoding='utf-8')
    main.app.state.atlas_implementation_executor = AtlasFileSafeApplyExecutor(workspace_root=repo)
    pool = _create_pool(c); pid = pool['pool_id']; iid = pool['plan_pool']['items'][0]['item_id']
    _set_project_path(tmp_path, pid, repo)
    _seed_patch_source(c, pid, iid, {'status':'approved','proposal_id':'pp1','risk_level':'low','target_files':['app.py'],'unified_diff_preview':'--- a/app.py\n+++ b/app.py\n@@\n-print("old")\n+print("new")\n'})
    _, draft_id = _create_and_approve_draft(c, pid, iid)
    r = c.post('/api/atlas/safe-apply/execute', json={'pool_id': pid, 'item_id': draft_id}).json()
    rr = c.post('/api/atlas/change-snapshots/restore', json={'pool_id': pid, 'item_id': draft_id, 'manifest_path': r['metadata']['change_snapshot']['manifest_path'], 'confirm_delete_missing_before': False}).json()
    assert rr['status'] == 'restored'
    assert (repo / 'app.py').read_text(encoding='utf-8') == 'print("old")\n'
    assert rr['result']['restored_count'] >= 1
    assert any(
        fr.get('path') == 'app.py' and fr.get('restored') is True
        for fr in rr['result'].get('file_results', [])
    )

def test_patch_proposal_draft_blocks_when_no_executable_change_content(tmp_path):
    _clear_safe_apply_state(); c = _client(tmp_path)
    repo = tmp_path / 'repo'; repo.mkdir(); (repo / 'app.py').write_text('print("old")\n', encoding='utf-8')
    main.app.state.atlas_implementation_executor = AtlasFileSafeApplyExecutor(workspace_root=repo)
    pool = _create_pool(c); pid = pool['pool_id']; iid = pool['plan_pool']['items'][0]['item_id']
    _set_project_path(tmp_path, pid, repo)
    _seed_patch_source(c, pid, iid, {'status':'approved','proposal_id':'pp1','risk_level':'low','target_files':['app.py']})
    _, draft_id = _create_and_approve_draft(c, pid, iid)
    r = c.post('/api/atlas/safe-apply/execute', json={'pool_id': pid, 'item_id': draft_id}).json()
    assert r['status'] in {'blocked', 'failed'}
    assert r['status'] != 'applied'
    reasons = []
    reasons.extend([str(x) for x in r.get('reason', [])] if isinstance(r.get('reason'), list) else [str(r.get('reason', ''))])
    reasons.extend([str(x) for x in r.get('warnings', [])])
    reasons.extend([str(x) for x in r.get('errors', [])])
    reasons.extend([str(x) for x in (r.get('metadata', {}).get('safe_apply_result', {}).get('reasons', []))])
    joined = ' '.join(reasons)
    assert ('content_missing' in joined) or ('unsupported_patch_format' in joined)
    assert (repo / 'app.py').read_text(encoding='utf-8') == 'print("old")\n'
    assert (r['metadata']['executor_result'].get('actual_file_changed') is False) or (r['metadata']['executor_result'].get('changed_files') == [])

def test_patch_proposal_draft_metadata_contains_executor_readable_patch(tmp_path):
    _clear_safe_apply_state(); c = _client(tmp_path)
    pool = _create_pool(c); pid = pool['pool_id']; iid = pool['plan_pool']['items'][0]['item_id']
    unified_diff_preview = '--- a/app.py\n+++ b/app.py\n@@\n-print("old")\n+print("new")\n'
    _seed_patch_source(c, pid, iid, {'status':'approved','proposal_id':'pp1','risk_level':'low','target_files':['app.py'],'unified_diff_preview': unified_diff_preview})
    b = c.post('/api/atlas/patch-proposals/planitem-draft', json={'pool_id': pid, 'item_id': iid, 'proposal_id': 'pp1'}).json()
    md = b['draft_item']['metadata']
    assert md['patch'] == unified_diff_preview
    assert md['unified_diff_preview'] == unified_diff_preview
    assert md['patch_proposal']['unified_diff_preview'] == unified_diff_preview
    assert md.get('patch') or md.get('proposed_content') or (md.get('patch_proposal') or {}).get('proposed_content') or (md.get('patch_proposal') or {}).get('unified_diff_preview')
