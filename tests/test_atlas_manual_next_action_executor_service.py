from pathlib import Path
from types import SimpleNamespace
import json
from agent.atlas_manual_next_action_executor_schema import AtlasManualNextActionExecutorRequest
from agent.atlas_manual_next_action_executor_service import AtlasManualNextActionExecutorService

class DummyPool: 
    def get_item(self, _): return None
class DummyStorage:
    def load_pool(self, _): return DummyPool()
    def save_pool(self, _): pass
class Journal:
    def __init__(self): self.events=[]
    def append_event(self, *a): self.events.append(a)
    def save_plan_pool(self, _): pass
class Svc:
    def __init__(self,name): self.name=name; self.called=0
    def decide(self, req): self.called+=1; return SimpleNamespace(model_dump=lambda:{'approval_run_id':'a1','decision':req.decision})
    def execute(self, req): self.called+=1; return SimpleNamespace(model_dump=lambda:{'execution_id':'e1'})
    def run(self, req): self.called+=1; return SimpleNamespace(model_dump=lambda:{'verification_run_id':'v1','supervised_retry_run_id':'r1','recommendation_exec_id':'p1'})

def _mk_orch(next_action='run_supervised_safe_apply', target='AtlasSupervisedHandoffSafeApplyService.execute'):
    p=Path('ca_data/atlas/next_action_orchestrator/p1'); p.mkdir(parents=True, exist_ok=True)
    d={'status':'action_ready','action_contract':{'item_id':'i1','next_action':next_action,'action_id':'a1','action_kind':'execution_candidate','target_service':target,'target_api_path':'/x','manual_required':True,'execution_allowed':False,'payload_valid':True,'payload':{'pool_id':'p1','item_id':'i1','handoff_id':'h1','safe_apply_execution_id':'s1','verification_run_id':'v1','recommendation_run_id':'rr1','regen_run_id':'rg1'}}}
    Path('ca_data/atlas/next_action_orchestrator/p1/nextaction_1.json').write_text(json.dumps(d),encoding='utf-8')

def _svc():
    j=Journal(); a=Svc('a'); s=Svc('s'); v=Svc('v'); r=Svc('r'); p=Svc('p')
    return AtlasManualNextActionExecutorService(storage=DummyStorage(),journal=j,approval_service=a,safe_apply_service=s,verification_service=v,retry_service=r,patch_regen_service=p),j,a,s,v,r,p

def test_dry_run_blocked_on_validation_error_and_no_service_called():
    _mk_orch(); svc,_,_,s,_,_,_=_svc()
    out=svc.execute(AtlasManualNextActionExecutorRequest(pool_id='p1',orchestrator_run_id='nextaction_1',dry_run=True,expected_next_action='approve_patch_candidate'))
    assert out.status=='blocked' and out.validation['executable'] is False and s.called==0

def test_dry_run_first_required_then_execute_after_dry_run():
    _mk_orch(); svc,_,_,s,_,_,_=_svc()
    blocked=svc.execute(AtlasManualNextActionExecutorRequest(pool_id='p1',orchestrator_run_id='nextaction_1',dry_run=False,confirmation_token='x',confirmation_text='EXECUTE ONE ACTION'))
    assert blocked.status=='blocked' and 'confirmation_required' in blocked.errors
    token='MANUAL_EXECUTE:nextaction_1:a1:run_supervised_safe_apply:i1'
    dry=svc.execute(AtlasManualNextActionExecutorRequest(pool_id='p1',orchestrator_run_id='nextaction_1',dry_run=True,confirmation_token=token,confirmation_text='EXECUTE ONE ACTION'))
    assert dry.status=='dry_run'
    exe=svc.execute(AtlasManualNextActionExecutorRequest(pool_id='p1',orchestrator_run_id='nextaction_1',dry_run=False,confirmation_token=token,confirmation_text='EXECUTE ONE ACTION'))
    assert exe.status=='executed' and s.called==1

def test_approval_requires_explicit_decision_and_ignores_suggested_decision():
    _mk_orch('approve_patch_candidate','AtlasPatchCandidateApprovalService.decide'); svc,_,a,_,_,_,_=_svc()
    token='MANUAL_EXECUTE:nextaction_1:a1:approve_patch_candidate:i1'
    out=svc.execute(AtlasManualNextActionExecutorRequest(pool_id='p1',orchestrator_run_id='nextaction_1',dry_run=False,confirmation_token=token,confirmation_text='EXECUTE ONE ACTION',explicit_decision=''))
    assert out.status=='blocked' and 'explicit_decision_required' in out.errors and a.called==0
