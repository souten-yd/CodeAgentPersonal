from pathlib import Path
import json
from fastapi.testclient import TestClient
from app.server import create_app


def _seed_pool(root):
    p = Path(root) / "atlas/plan_pools"
    p.mkdir(parents=True, exist_ok=True)
    pool = {"pool_id":"p1","root_goal":"g","items":[{"pool_id":"p1","item_id":"i1","title":"i1","goal":"g","status":"queued","metadata":{}}],"created_at":"","updated_at":""}
    (p / "p1.json").write_text(json.dumps(pool), encoding="utf-8")



def test_guarded_loop_advance_to_confirmation_all_artifacts_same_root(tmp_path):
    app = create_app(); app.state.atlas_ca_data_root = tmp_path
    _seed_pool(tmp_path)
    c = TestClient(app)
    r = c.post('/api/atlas/guarded-operator-loop/run', json={'pool_id':'p1','mode':'advance_to_confirmation','run_id':'r1'})
    assert r.status_code == 200
    assert list((tmp_path / 'atlas/multi_item_supervised_status/p1').glob('multistatus_*.json'))
    assert list((tmp_path / 'atlas/next_action_orchestrator/p1').glob('nextaction_*.json'))
    o = sorted((tmp_path / 'atlas/next_action_orchestrator/p1').glob('nextaction_*.json'))[-1].stem
    c.post('/api/atlas/guarded-operator-loop/run', json={'pool_id':'p1','mode':'dry_run_next_action','orchestrator_run_id':o,'action_id':'a1','expected_next_action':'approve_patch_candidate'})
    assert list((tmp_path / 'atlas/manual_next_action_executor/p1').glob('manualexec_*.json'))
    assert list((tmp_path / 'atlas/guarded_operator_loop/p1').glob('guardloop_*.json'))


def test_guarded_loop_dry_run_next_action_reads_orchestrator_from_same_root(tmp_path):
    app = create_app(); app.state.atlas_ca_data_root = tmp_path
    _seed_pool(tmp_path)
    c = TestClient(app)
    m = c.post('/api/atlas/multi-item-supervised-status/build', json={'pool_id':'p1','run_id':'r1'}).json()['multi_status_run_id']
    o = c.post('/api/atlas/next-action-orchestrator/prepare', json={'pool_id':'p1','run_id':'r1','multi_status_run_id':m}).json()['orchestrator_run_id']
    d = c.post('/api/atlas/guarded-operator-loop/run', json={'pool_id':'p1','mode':'dry_run_next_action','orchestrator_run_id':o,'action_id':'a1','expected_next_action':'approve_patch_candidate'})
    assert d.status_code == 200
    token = d.json().get('confirmation_token') or ''
    assert token == '' or token.startswith('MANUAL_EXECUTE:')
