import json
from pathlib import Path
from agent.atlas_journal import AtlasJournal
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.atlas_post_manual_execution_refresh_schema import AtlasPostManualExecutionRefreshRequest
from agent.atlas_post_manual_execution_refresh_service import AtlasPostManualExecutionRefreshService

class X: 
    def __init__(self, **k): self.__dict__.update(k)
    def model_dump(self): return self.__dict__


def setup(tmp_path):
    st=AtlasPlanPoolStorage(tmp_path/'ca_data'); jr=AtlasJournal(tmp_path/'ca_data')
    pool=AtlasPlanPool(pool_id='p1', root_goal='g', items=[AtlasPlanItem(item_id='i1', pool_id='p1', title='t', goal='g1', status='ready', metadata={})])
    st.save_pool(pool)
    root=tmp_path/'ca_data'/'atlas'/'manual_next_action_executor'/'p1'; root.mkdir(parents=True)
    m={"pool_id":"p1","status":"executed","executor_run_id":"manualexec_1","selected_item_id":"i1","selected_next_action":"run_supervised_safe_apply","action_contract":{"x":1},"metadata":{"side_effects":{}},"execution_result_id":"e1"}
    (root/'manualexec_1.json').write_text(json.dumps(m),encoding='utf-8')
    svc=AtlasPostManualExecutionRefreshService(storage=st,journal=jr,supervised_item_status_service=X(finalize=lambda *_a,**_k:X(finalize_run_id='f1',supervised_status_after='safe_apply_ready',next_action='run_supervised_safe_apply')),multi_status_service=X(build_status=lambda *_a,**_k:X(multi_status_run_id='m1',counts={'safe_apply_ready':1},next_item={'item_id':'i1','next_action':'run_supervised_safe_apply'})),next_action_orchestrator_service=X(prepare=lambda *_a,**_k:X(orchestrator_run_id='n1',selected_item_id='i1',selected_next_action='run_supervised_safe_apply',action_contract={'payload_valid':True})))
    return svc, st

def test_refresh_loads_manual_executor_result(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    svc,_=setup(tmp_path)
    r=svc.refresh(AtlasPostManualExecutionRefreshRequest(pool_id='p1', executor_run_id='manualexec_1'))
    assert r.status=='refreshed' and r.manual_execution_result['selected_item_id']=='i1'

def test_blocks_invalid_executor_status(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    svc,_=setup(tmp_path)
    p=tmp_path/'ca_data'/'atlas'/'manual_next_action_executor'/'p1'/'manualexec_1.json'; d=json.loads(p.read_text()); d['status']='blocked'; p.write_text(json.dumps(d))
    r=svc.refresh(AtlasPostManualExecutionRefreshRequest(pool_id='p1', executor_run_id='manualexec_1'))
    assert r.status=='blocked'
