from pathlib import Path

from fastapi.testclient import TestClient

import main
from agent.atlas_journal import AtlasJournal
from agent.atlas_patch_proposal_schema import AtlasPatchProposalRequest
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage


def _client(tmp_path):
    main.app.state.atlas_ca_data_dir = str(tmp_path)
    main.app.state.atlas_llm_json_fn = None
    return TestClient(main.app)


def _create_pool(c):
    item = AtlasPlanItem(
        item_id='i1',
        pool_id='p1',
        title='Patch proposal item',
        goal='patch proposal',
        item_type='implementation',
        status='ready',
        risk_level='low',
        target_files=['a.py'],
        metadata={'action_type': 'update'},
    )
    pool = AtlasPlanPool(
        pool_id='p1',
        root_goal='patch proposal',
        project_path=str(Path(c.app.state.atlas_ca_data_dir)),
        status='ready',
        items=[item],
    )
    storage = AtlasPlanPoolStorage(Path(c.app.state.atlas_ca_data_dir))
    journal = AtlasJournal(Path(c.app.state.atlas_ca_data_dir), workspace_id='default')
    storage.save_pool(pool)
    journal.save_plan_pool(pool)
    payload = pool.model_dump()
    return {'pool_id': pool.pool_id, 'plan_pool': payload, **payload}


def _set_debug_review(c, pool_id, item_id, analyzed=True):
    storage = AtlasPlanPoolStorage(Path(c.app.state.atlas_ca_data_dir))
    journal = AtlasJournal(Path(c.app.state.atlas_ca_data_dir), workspace_id='default')
    pool = storage.load_pool(pool_id)
    item = pool.get_item(item_id)
    item.metadata.setdefault('debug_review', {})
    item.metadata['debug_review'] = {
        'status': 'analyzed' if analyzed else 'failed',
        'root_cause_category': 'test_failure',
        'proposed_fix': 'Adjust failing assertion and update guard logic.',
    }
    storage.save_pool(pool)
    journal.save_plan_pool(pool)


def test_patch_proposal_requires_debug_review_analyzed(tmp_path):
    # When the item has debug_review metadata but it is not yet analyzed, patch generation must be
    # blocked.  Items with NO debug_review data are treated as plain plan items and are not blocked.
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]
    _set_debug_review(c, pool['pool_id'], item['item_id'], analyzed=False)
    body = c.post('/api/atlas/patch-proposals/generate', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'r1'}).json()
    assert body['status'] == 'blocked' and 'debug_review_not_analyzed' in body['warnings']


def test_patch_proposal_generates_from_debug_review_with_fallback(tmp_path):
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]; _set_debug_review(c, pool['pool_id'], item['item_id'])
    body = c.post('/api/atlas/patch-proposals/generate', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'r2'}).json()
    assert body['status'] == 'proposed'
    assert body['proposal']['proposed_fix'] and body['proposal']['target_files'] is not None
    assert body['proposal']['summary'] or body['proposal']['title']
    assert body['proposal'].get('warnings') is not None


def test_patch_proposal_uses_injected_llm_json_fn(tmp_path):
    c = _client(tmp_path)
    c.app.state.atlas_llm_json_fn = lambda s, u: {'summary': 'from llm', 'proposed_fix': 'llm fix', 'target_files': ['a.py'], 'risk_level': 'low'}
    pool = _create_pool(c); item = pool['plan_pool']['items'][0]; _set_debug_review(c, pool['pool_id'], item['item_id'])
    body = c.post('/api/atlas/patch-proposals/generate', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'r3'}).json()
    assert body['status'] == 'proposed' and body['proposal']['summary'] == 'from llm' and body['proposal']['risk_level'] == 'low'


def test_patch_proposal_record_saved_and_event(tmp_path):
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]; _set_debug_review(c, pool['pool_id'], item['item_id'])
    body = c.post('/api/atlas/patch-proposals/generate', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'r4'}).json()
    assert Path(body['proposal_json_path']).exists() and Path(body['proposal_md_path']).exists()
    events = '\n'.join(p.read_text(encoding='utf-8') for p in Path(tmp_path).rglob('events.ndjson'))
    assert 'patch_generation_failed' in events
    md = Path(body['proposal_md_path']).read_text(encoding='utf-8')
    assert 'No patch was applied.' in md and 'No safe_apply was run.' in md and 'No verification rerun was performed.' in md


def test_patch_proposal_updates_item_metadata(tmp_path):
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]; _set_debug_review(c, pool['pool_id'], item['item_id'])
    c.post('/api/atlas/patch-proposals/generate', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'r5'})
    after = c.get(f"/api/atlas/plan-pools/{pool['pool_id']}").json()['plan_pool']
    meta = next(i for i in after['items'] if i['item_id'] == item['item_id'])['metadata']['patch_proposal']
    assert meta['status'] == 'proposed' and meta['proposal_json_path'] and meta['proposal_md_path']


def test_patch_proposal_response_includes_recovery_orchestration_continuation(tmp_path):
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]; _set_debug_review(c, pool['pool_id'], item['item_id'])
    body = c.post('/api/atlas/patch-proposals/generate', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'r6'}).json()
    assert body.get('recovery_summary') and body.get('orchestration_summary') and body.get('continuation_prompt')


def test_patch_proposal_does_not_apply_or_verify():
    src = Path('agent/atlas_patch_proposal_service.py').read_text(encoding='utf-8')
    for t in ('safe_apply(', 'execute_safe_apply', 'runVerification', 'TestCommandRunner(', 'ImplementationExecutor', 'subprocess', 'shell=True', 'run_command('):
        assert t not in src


def test_no_patch_apply_or_batch_routes(tmp_path):
    c = _client(tmp_path)
    assert c.post('/api/atlas/patch-proposals/generate', json={'pool_id': 'x', 'item_id': 'y'}).status_code in {200, 400}
    assert c.post('/api/atlas/patch-proposals/apply', json={}).status_code in {404, 405}
    assert c.post('/api/atlas/patch-proposals/batch', json={}).status_code in {404, 405}


def test_patch_proposal_request_has_no_patch_command_apply_fields():
    fields = set(AtlasPatchProposalRequest.model_fields.keys())
    for forbidden in ('patch', 'command', 'apply', 'shell', 'execute'):
        assert forbidden not in fields


def test_patch_proposal_ignores_llm_status_applied(tmp_path):
    c = _client(tmp_path)
    c.app.state.atlas_llm_json_fn = lambda s, u: {
        'status': 'applied',
        'proposal_id': 'malicious',
        'pool_id': 'other',
        'item_id': 'other_item',
        'run_id': 'other_run',
        'summary': 'from llm',
        'proposed_fix': 'safe proposal',
    }
    pool = _create_pool(c); item = pool['plan_pool']['items'][0]; _set_debug_review(c, pool['pool_id'], item['item_id'])
    body = c.post('/api/atlas/patch-proposals/generate', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'r7'}).json()
    assert body['status'] == 'proposed'
    assert body['proposal']['status'] == 'proposed'
    assert body['proposal']['pool_id'] == pool['pool_id']
    assert body['proposal']['item_id'] == item['item_id']
    assert body['proposal']['run_id'] == 'r7'
    assert 'llm_untrusted_fields_ignored' in body['proposal']['warnings']


def test_patch_proposal_normalizes_invalid_risk_level(tmp_path):
    c = _client(tmp_path)
    c.app.state.atlas_llm_json_fn = lambda s, u: {'risk_level': 'please_apply_now', 'proposed_fix': 'x'}
    pool = _create_pool(c); item = pool['plan_pool']['items'][0]; _set_debug_review(c, pool['pool_id'], item['item_id'])
    body = c.post('/api/atlas/patch-proposals/generate', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'r8'}).json()
    assert body['proposal']['risk_level'] == 'medium'
    assert 'llm_risk_level_normalized' in body['proposal']['warnings']


def test_patch_proposal_filters_unsafe_target_files(tmp_path):
    c = _client(tmp_path)
    c.app.state.atlas_llm_json_fn = lambda s, u: {'target_files': ['../secret', '/etc/passwd', 'safe.py'], 'proposed_fix': 'x'}
    pool = _create_pool(c); item = pool['plan_pool']['items'][0]; _set_debug_review(c, pool['pool_id'], item['item_id'])
    body = c.post('/api/atlas/patch-proposals/generate', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'r9'}).json()
    assert body['proposal']['target_files'] == ['safe.py']
    assert 'unsafe_target_files_ignored' in body['proposal']['warnings']


def test_patch_proposal_truncates_large_diff_preview(tmp_path):
    c = _client(tmp_path)
    c.app.state.atlas_llm_json_fn = lambda s, u: {'unified_diff_preview': 'x' * 20000, 'proposed_fix': 'x'}
    pool = _create_pool(c); item = pool['plan_pool']['items'][0]; _set_debug_review(c, pool['pool_id'], item['item_id'])
    body = c.post('/api/atlas/patch-proposals/generate', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'r10'}).json()
    assert len(body['proposal']['unified_diff_preview']) <= 12000
    assert 'diff_preview_truncated' in body['proposal']['warnings']


def test_patch_proposal_needs_revision_regeneration_policy(tmp_path):
    c = _client(tmp_path); pool = _create_pool(c); item = pool['plan_pool']['items'][0]
    _set_debug_review(c, pool['pool_id'], item['item_id'])
    first = c.post('/api/atlas/patch-proposals/generate', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'nr1'}).json()
    c.post('/api/atlas/patch-proposals/decide', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'proposal_id': first['proposal']['proposal_id'], 'run_id': 'nr2', 'decision': 'needs_revision'})
    second = c.post('/api/atlas/patch-proposals/generate', json={'pool_id': pool['pool_id'], 'item_id': item['item_id'], 'run_id': 'nr3'}).json()
    assert second['status'] == 'proposed'
    assert second['proposal']['proposal_id'] != first['proposal']['proposal_id']
    after = c.get(f"/api/atlas/plan-pools/{pool['pool_id']}").json()['plan_pool']
    meta = next(i for i in after['items'] if i['item_id'] == item['item_id'])['metadata']
    assert int(meta['patch_proposal_revision_count']) >= 2
