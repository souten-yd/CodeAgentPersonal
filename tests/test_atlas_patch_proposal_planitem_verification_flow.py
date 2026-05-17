from pathlib import Path
import json

from fastapi.testclient import TestClient

import main

DASH = Path('web/js/atlas_dashboard.js').read_text(encoding='utf-8')


def _client(tmp_path):
    main.app.state.atlas_ca_data_dir = str(tmp_path)
    return TestClient(main.app)


def _seed(c):
    pool = c.post('/api/atlas/plan-pools', json={'input': 'x'}).json()['plan_pool']
    return pool['pool_id'], pool['items'][0]['item_id']


def _pool_path(tmp_path, pool_id):
    return Path(tmp_path) / 'atlas' / 'workspaces' / 'default' / 'plan_pools' / pool_id / 'plan_pool.json'


def _set_item(tmp_path, pool_id, item_id, *, status='completed', metadata=None):
    p = _pool_path(tmp_path, pool_id)
    pool = json.loads(p.read_text(encoding='utf-8'))
    for it in pool['items']:
        if it['item_id'] == item_id:
            it['status'] = status
            it.setdefault('metadata', {}).update(metadata or {})
    p.write_text(json.dumps(pool, ensure_ascii=False, indent=2), encoding='utf-8')


def test_draft_safe_apply_result_appears_as_verification_candidate_contract():
    assert "['applied','simulated'].includes(safe) || ['completed','applied'].includes(st)" in DASH
    assert 'Patch Proposal Draft' in DASH
    assert 'Manual verification only.' in DASH


def test_manual_verification_failed_does_not_start_debug_loop(tmp_path):
    c = _client(tmp_path)
    pool_id, item_id = _seed(c)
    _set_item(tmp_path, pool_id, item_id, metadata={'safe_apply': {'status': 'applied', 'source': 'patch_proposal_planitem_draft', 'source_proposal_id': 'p1'}})

    class _Res:
        def model_dump(self):
            return {'status': 'failed', 'command': 'python -m py_compile app/main.py'}

    class _Batch:
        results = [_Res()]

    class _Runner:
        def run_many(self, reqs, stop_on_failure=False):
            return _Batch()

    main.app.state.atlas_test_command_runner = _Runner()
    r = c.post('/api/atlas/verification/run', json={'pool_id': pool_id, 'item_id': item_id, 'run_id': 'r1'}).json()
    assert r['status'] == 'failed'
    events = (Path(tmp_path) / 'atlas' / 'workspaces' / 'default' / 'plan_pools' / pool_id / 'pipeline_runs' / 'r1' / 'events.ndjson').read_text(encoding='utf-8')
    assert 'debug_review_manual_started' not in events


def test_verification_preserves_draft_source_metadata(tmp_path):
    c = _client(tmp_path)
    pool_id, item_id = _seed(c)
    _set_item(tmp_path, pool_id, item_id, metadata={'safe_apply': {'status': 'applied', 'source': 'patch_proposal_planitem_draft', 'source_proposal_id': 'p1'}})

    class _Res:
        def model_dump(self):
            return {'status': 'passed', 'command': 'python -m py_compile app/main.py'}

    class _Batch:
        results = [_Res()]

    class _Runner:
        def run_many(self, reqs, stop_on_failure=False):
            return _Batch()

    main.app.state.atlas_test_command_runner = _Runner()
    r = c.post('/api/atlas/verification/run', json={'pool_id': pool_id, 'item_id': item_id}).json()
    item = next(i for i in r['plan_pool']['items'] if i['item_id'] == item_id)
    v = item['metadata']['verification']
    assert v['source'] == 'patch_proposal_planitem_draft'
    assert v['source_proposal_id'] == 'p1'
    assert v['manual_only'] is True and v['auto_debug'] is False
