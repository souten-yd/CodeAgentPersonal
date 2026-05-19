import json
from pathlib import Path
from fastapi.testclient import TestClient

from app.server import create_app
from agent.atlas_manual_next_action_executor_service import AtlasManualNextActionExecutorService
from agent.atlas_manual_next_action_executor_schema import AtlasManualNextActionExecutorRequest

class DummyPool:
    def get_item(self, _): return None
class DummyStorage:
    def load_pool(self, _): return DummyPool()
    def save_pool(self, _): pass
class DummyJournal:
    def append_event(self, *a): pass
    def save_plan_pool(self, _): pass
class Svc:
    def decide(self, req): return type('X', (), {'model_dump': lambda self: {'approval_run_id': 'a1', 'decision': req.decision}})()
    def execute(self, req): return type('X', (), {'model_dump': lambda self: {'execution_id': 'e1'}})()
    def run(self, req): return type('X', (), {'model_dump': lambda self: {'verification_run_id': 'v1'}})()

def _mk_service(tmp_path: Path):
    return AtlasManualNextActionExecutorService(storage=DummyStorage(), journal=DummyJournal(), approval_service=Svc(), safe_apply_service=Svc(), verification_service=Svc(), retry_service=Svc(), patch_regen_service=Svc(), data_root=tmp_path)

def _write_orch(tmp_path: Path):
    p = tmp_path / 'atlas' / 'next_action_orchestrator' / 'p1'; p.mkdir(parents=True, exist_ok=True)
    d = {'status':'action_ready','action_contract':{'item_id':'i1','next_action':'run_supervised_safe_apply','action_id':'a1','action_kind':'execution_candidate','target_service':'AtlasSupervisedHandoffSafeApplyService.execute','target_api_path':'/x','manual_required':True,'execution_allowed':False,'payload_valid':True,'payload':{'pool_id':'p1','item_id':'i1','handoff_id':'h1'}}}
    (p / 'nextaction_1.json').write_text(json.dumps(d), encoding='utf-8')

def test_manual_executor_uses_injected_data_root_for_orchestrator_load(tmp_path):
    _write_orch(tmp_path)
    out = _mk_service(tmp_path).execute(AtlasManualNextActionExecutorRequest(pool_id='p1', orchestrator_run_id='nextaction_1', dry_run=True))
    assert out.status == 'dry_run'

def test_manual_executor_saved_json_contains_final_metadata(tmp_path):
    _write_orch(tmp_path)
    token='MANUAL_EXECUTE:nextaction_1:a1:run_supervised_safe_apply:i1'
    svc = _mk_service(tmp_path)
    svc.execute(AtlasManualNextActionExecutorRequest(pool_id='p1', orchestrator_run_id='nextaction_1', dry_run=True))
    out = svc.execute(AtlasManualNextActionExecutorRequest(pool_id='p1', orchestrator_run_id='nextaction_1', dry_run=False, confirmation_token=token, confirmation_text='EXECUTE ONE ACTION'))
    saved = json.loads((tmp_path / 'atlas' / 'manual_next_action_executor' / 'p1' / f'{out.executor_run_id}.json').read_text())
    assert 'side_effects' in saved['metadata'] and 'dry_run_first_satisfied' in saved['metadata'] and 'confirmation_valid' in saved['metadata']

def test_manual_executor_result_and_latest_api_use_request_root(tmp_path):
    app = create_app(); app.state.atlas_ca_data_root = str(tmp_path)
    _write_orch(tmp_path)
    c = TestClient(app)
    ex = c.post('/api/atlas/manual-next-action-executor/execute', json={'pool_id':'p1','orchestrator_run_id':'nextaction_1','dry_run':True}).json()
    rr = c.get(f"/api/atlas/manual-next-action-executor/results/p1/{ex['executor_run_id']}")
    lr = c.post('/api/atlas/manual-next-action-executor/latest', json={'pool_id':'p1'})
    assert rr.status_code == 200 and lr.status_code == 200
