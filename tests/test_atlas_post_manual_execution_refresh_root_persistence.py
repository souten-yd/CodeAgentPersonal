import json
from fastapi.testclient import TestClient

from app.server import create_app
from agent.atlas_post_manual_execution_refresh_schema import AtlasPostManualExecutionRefreshRequest
from agent.atlas_post_manual_execution_refresh_service import AtlasPostManualExecutionRefreshService

class X:
    def __init__(self, **k): self.__dict__.update(k)
    def model_dump(self): return self.__dict__
class DummyStorage:
    def load_pool(self, _):
        class P:
            def get_item(self, __): return None
        return P()
    def save_pool(self, _): pass
class DummyJournal:
    def append_event(self, *a): pass
    def save_plan_pool(self, _): pass

def _svc(root):
    return AtlasPostManualExecutionRefreshService(storage=DummyStorage(), journal=DummyJournal(), supervised_item_status_service=X(finalize=lambda *_a, **_k: X(finalize_run_id='f1')), multi_status_service=X(build_status=lambda *_a, **_k: X(multi_status_run_id='m1', counts={}, next_item={'item_id':'i1','next_action':'run_supervised_safe_apply'})), next_action_orchestrator_service=X(prepare=lambda *_a, **_k: X(orchestrator_run_id='n1', selected_item_id='i1', selected_next_action='run_supervised_safe_apply', action_contract={'payload_valid': True})), data_root=root)

def test_post_refresh_uses_injected_data_root_for_manualexec_load(tmp_path):
    p=tmp_path/'atlas'/'manual_next_action_executor'/'p1'; p.mkdir(parents=True)
    (p/'manualexec_1.json').write_text(json.dumps({'pool_id':'p1','status':'executed','executor_run_id':'manualexec_1','selected_item_id':'i1','selected_next_action':'run_supervised_safe_apply','action_contract':{'x':1},'metadata':{'side_effects':{}},'execution_result_id':'e1'}))
    r = _svc(tmp_path).refresh(AtlasPostManualExecutionRefreshRequest(pool_id='p1', executor_run_id='manualexec_1'))
    assert r.status in {'refreshed','partial'}

def test_post_refresh_result_and_latest_api_use_request_root(tmp_path):
    app=create_app(); app.state.atlas_ca_data_root=str(tmp_path)
    manual=tmp_path/'atlas'/'manual_next_action_executor'/'p1'; manual.mkdir(parents=True)
    (manual/'manualexec_1.json').write_text(json.dumps({'pool_id':'p1','status':'executed','executor_run_id':'manualexec_1','selected_item_id':'i1','selected_next_action':'run_supervised_safe_apply','action_contract':{'x':1},'metadata':{'side_effects':{}},'execution_result_id':'e1'}))
    c=TestClient(app)
    out=c.post('/api/atlas/post-manual-execution-refresh/refresh', json={'pool_id':'p1','executor_run_id':'manualexec_1'}).json()
    rr=c.get(f"/api/atlas/post-manual-execution-refresh/results/p1/{out['refresh_run_id']}")
    lr=c.post('/api/atlas/post-manual-execution-refresh/latest', json={'pool_id':'p1'})
    assert rr.status_code==200 and lr.status_code==200

def test_no_new_path_ca_data_literals_in_manual_executor_stack():
    targets=[
        'agent/atlas_manual_next_action_executor_service.py',
        'agent/atlas_post_manual_execution_refresh_service.py',
        'app/api/atlas_manual_next_action_executor.py',
        'app/api/atlas_post_manual_execution_refresh.py',
    ]
    for t in targets:
        text=open(t, encoding='utf-8').read()
        assert 'Path("ca_data")' not in text
