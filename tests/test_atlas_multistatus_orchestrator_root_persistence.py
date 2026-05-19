import json
from pathlib import Path
from fastapi.testclient import TestClient

from agent.atlas_multi_item_supervised_status_schema import AtlasMultiItemSupervisedStatusRequest
from agent.atlas_multi_item_supervised_status_service import AtlasMultiItemSupervisedStatusService
from agent.atlas_next_action_orchestrator_schema import AtlasNextActionOrchestratorRequest
from agent.atlas_next_action_orchestrator_service import AtlasNextActionOrchestratorService
from app.server import create_app
from tests.test_atlas_multi_item_supervised_status_service import DummyFinalize, DummyStorage, RecordingJournal, mk_pool


def _seed_pool(root):
    p = Path(root) / "atlas/plan_pools"
    p.mkdir(parents=True, exist_ok=True)
    pool = {"pool_id":"p1","root_goal":"g","items":[{"pool_id":"p1","item_id":"i1","title":"i1","goal":"g","status":"queued","metadata":{}}],"created_at":"","updated_at":""}
    (p / "p1.json").write_text(json.dumps(pool), encoding="utf-8")


def _services(tmp_path):
    j = RecordingJournal()
    ms = AtlasMultiItemSupervisedStatusService(storage=DummyStorage(mk_pool()), journal=j, supervised_item_status_service=DummyFinalize(), data_root=tmp_path)
    no = AtlasNextActionOrchestratorService(storage=DummyStorage(mk_pool()), journal=j, supervised_status_service=ms, data_root=tmp_path)
    return ms, no


def test_multi_status_service_uses_injected_data_root(tmp_path):
    ms, _ = _services(tmp_path)
    r = ms.build_status(AtlasMultiItemSupervisedStatusRequest(pool_id='p1', run_id='r1'))
    assert (tmp_path / 'atlas/multi_item_supervised_status/p1' / f'{r.multi_status_run_id}.json').exists()


def test_multi_status_saved_json_contains_result_paths(tmp_path):
    ms, _ = _services(tmp_path)
    r = ms.build_status(AtlasMultiItemSupervisedStatusRequest(pool_id='p1', run_id='r1'))
    p = tmp_path / 'atlas/multi_item_supervised_status/p1' / f'{r.multi_status_run_id}.json'
    d = json.loads(p.read_text())
    md = d['metadata']
    assert md['data_root'] == str(tmp_path.resolve())
    assert md['result_path'].endswith('.json')
    assert md['result_path_relative'].startswith('atlas/multi_item_supervised_status/p1/')
    assert md['md_path_relative'].endswith('.md')


def test_next_action_orchestrator_uses_injected_data_root_to_load_queue(tmp_path):
    ms, no = _services(tmp_path)
    m = ms.build_status(AtlasMultiItemSupervisedStatusRequest(pool_id='p1', run_id='r1'))
    out = no.prepare(AtlasNextActionOrchestratorRequest(pool_id='p1', run_id='r1', multi_status_run_id=m.multi_status_run_id))
    assert out.orchestrator_run_id.startswith('nextaction_')


def test_next_action_orchestrator_saves_result_under_injected_data_root(tmp_path):
    ms, no = _services(tmp_path)
    m = ms.build_status(AtlasMultiItemSupervisedStatusRequest(pool_id='p1', run_id='r1'))
    out = no.prepare(AtlasNextActionOrchestratorRequest(pool_id='p1', run_id='r1', multi_status_run_id=m.multi_status_run_id))
    p = tmp_path / 'atlas/next_action_orchestrator/p1' / f'{out.orchestrator_run_id}.json'
    assert p.exists()
    assert json.loads(p.read_text())['metadata']['result_path_relative'].startswith('atlas/next_action_orchestrator/p1/')


def test_multi_status_api_uses_request_root(tmp_path):
    app = create_app()
    app.state.atlas_ca_data_root = tmp_path
    _seed_pool(tmp_path)
    c = TestClient(app)
    b = c.post('/api/atlas/multi-item-supervised-status/build', json={'pool_id': 'p1', 'run_id': 'r1'})
    assert b.status_code == 200
    rid = b.json()['multi_status_run_id']
    assert c.get(f'/api/atlas/multi-item-supervised-status/results/p1/{rid}').status_code == 200
    assert c.post('/api/atlas/multi-item-supervised-status/latest', json={'pool_id': 'p1'}).status_code == 200


def test_next_action_orchestrator_api_uses_request_root(tmp_path):
    app = create_app(); app.state.atlas_ca_data_root = tmp_path
    _seed_pool(tmp_path)
    c = TestClient(app)
    m = c.post('/api/atlas/multi-item-supervised-status/build', json={'pool_id':'p1','run_id':'r1'}).json()['multi_status_run_id']
    p = c.post('/api/atlas/next-action-orchestrator/prepare', json={'pool_id':'p1','run_id':'r1','multi_status_run_id':m})
    assert p.status_code == 200
    oid = p.json()['orchestrator_run_id']
    assert c.get(f'/api/atlas/next-action-orchestrator/results/p1/{oid}').status_code == 200
    assert c.post('/api/atlas/next-action-orchestrator/latest', json={'pool_id':'p1'}).status_code == 200


def test_no_path_ca_data_literals_in_multistatus_orchestrator_stack():
    files = [
        'agent/atlas_multi_item_supervised_status_service.py',
        'agent/atlas_next_action_orchestrator_service.py',
        'app/api/atlas_multi_item_supervised_status.py',
        'app/api/atlas_next_action_orchestrator.py',
        'app/api/atlas_guarded_operator_loop.py',
    ]
    banned = ['Path("ca_data")', "Path('ca_data')", 'AtlasPlanPoolStorage("ca_data")', "AtlasPlanPoolStorage('ca_data')", 'AtlasJournal("ca_data")', "AtlasJournal('ca_data')"]
    for f in files:
        t = Path(f).read_text(encoding='utf-8')
        for b in banned:
            assert b not in t
