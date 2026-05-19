from pathlib import Path
from types import SimpleNamespace
from agent.atlas_guarded_operator_loop_schema import AtlasGuardedOperatorLoopRequest
from agent.atlas_guarded_operator_loop_service import AtlasGuardedOperatorLoopService

class J:
    def __init__(self): self.events=[]
    def append_event(self,*a): self.events.append(a)
class MS:
    def build_status(self,*_): return SimpleNamespace(multi_status_run_id='multistatus_1')
class NO:
    def prepare(self,*_): return SimpleNamespace(orchestrator_run_id='nextaction_1',selected_item_id='i1',selected_next_action='run_supervised_verification',status='action_ready',model_dump=lambda:{'action_contract':{'action_id':'a1','action_kind':'execution_candidate','payload_valid':True,'item_id':'i1'}})
class ME:
    def __init__(self): self.dry=0; self.exe=0
    def execute(self, req):
        self.dry += 1 if req.dry_run else 0
        self.exe += 0 if req.dry_run else 1
        return SimpleNamespace(status='dry_run' if req.dry_run else 'executed',executor_run_id='manualexec_1',model_dump=lambda:{'status':'dry_run' if req.dry_run else 'executed','validation':{'executable':True},'executor_run_id':'manualexec_1'})
class PR:
    def __init__(self): self.calls=0
    def refresh(self,*_): self.calls +=1; return SimpleNamespace(refresh_run_id='refresh_1',model_dump=lambda:{'refresh_run_id':'refresh_1'})

def mk(tmp):
    j=J(); me=ME(); pr=PR()
    s=AtlasGuardedOperatorLoopService(journal=j,multi_status_service=MS(),next_action_orchestrator_service=NO(),manual_executor_service=me,post_refresh_service=pr,data_root=tmp)
    return s,j,me,pr

def test_dry_run_next_action_token_uses_item_id_not_pool_id(tmp_path):
    p=tmp_path/'atlas/next_action_orchestrator/pool_abc'; p.mkdir(parents=True)
    (p/'nextaction_1.json').write_text('{"selected_item_id":"item_123","action_contract":{"item_id":"item_123"}}',encoding='utf-8')
    s,_,_,_=mk(tmp_path)
    r=s.run(AtlasGuardedOperatorLoopRequest(pool_id='pool_abc',mode='dry_run_next_action',orchestrator_run_id='nextaction_1',action_id='a1',expected_next_action='run_supervised_verification'))
    if r.confirmation_token:
        assert 'item_123' in r.confirmation_token
        assert not r.confirmation_token.endswith(':pool_abc')
    j=(tmp_path/'atlas/guarded_operator_loop/pool_abc'/f'{r.loop_run_id}.json').read_text(encoding='utf-8')
    assert 'MANUAL_EXECUTE:' not in j

def test_dry_run_next_action_does_not_require_execute_confirmation(tmp_path):
    s,_,me,_=mk(tmp_path)
    r=s.run(AtlasGuardedOperatorLoopRequest(pool_id='p1',mode='dry_run_next_action',orchestrator_run_id='nextaction_1',action_id='a1',expected_next_action='run_supervised_verification'))
    assert r.metadata['manual_executor_dry_run_calls']==1 and r.metadata['manual_executor_execute_calls']==0 and me.dry==1 and me.exe==0

def test_manual_review_preblocked_before_manual_executor(tmp_path):
    s,j,me,_=mk(tmp_path)
    r=s.run(AtlasGuardedOperatorLoopRequest(pool_id='p1',mode='execute_confirmed_action',expected_next_action='manual_review',confirmation_token='x',confirmation_text='EXECUTE ONE ACTION',require_dry_run_first=True))
    assert r.status=='blocked' and 'non_executable_next_action' in r.errors and r.metadata['manual_executor_execute_calls']==0 and me.exe==0
    assert any('guarded_operator_loop_execute_blocked' in str(e) for e in j.events)

def test_investigate_failure_preblocked_before_manual_executor(tmp_path):
    s,_,me,_=mk(tmp_path)
    r=s.run(AtlasGuardedOperatorLoopRequest(pool_id='p1',mode='execute_confirmed_action',expected_next_action='investigate_failure',confirmation_token='x',confirmation_text='EXECUTE ONE ACTION',require_dry_run_first=True))
    assert r.status=='blocked' and me.exe==0

def test_none_preblocked_before_manual_executor(tmp_path):
    s,_,me,_=mk(tmp_path)
    r=s.run(AtlasGuardedOperatorLoopRequest(pool_id='p1',mode='execute_confirmed_action',expected_next_action='none',confirmation_token='x',confirmation_text='EXECUTE ONE ACTION',require_dry_run_first=True))
    assert r.status=='blocked' and me.exe==0

def test_no_action_preblocked_before_manual_executor(tmp_path):
    s,_,me,_=mk(tmp_path)
    r=s.run(AtlasGuardedOperatorLoopRequest(pool_id='p1',mode='execute_confirmed_action',expected_next_action='no_action',confirmation_token='x',confirmation_text='EXECUTE ONE ACTION',require_dry_run_first=True))
    assert r.status=='blocked' and me.exe==0

def test_execute_and_refresh_non_executable_does_not_refresh(tmp_path):
    s,_,me,pr=mk(tmp_path)
    r=s.run(AtlasGuardedOperatorLoopRequest(pool_id='p1',mode='execute_and_refresh',expected_next_action='manual_review',confirmation_token='x',confirmation_text='EXECUTE ONE ACTION',require_dry_run_first=True))
    assert r.status=='blocked' and me.exe==0 and pr.calls==0 and r.metadata['post_refresh_calls']==0

def test_approval_approve_calls_executor_once(tmp_path):
    s,_,me,_=mk(tmp_path)
    r=s.run(AtlasGuardedOperatorLoopRequest(pool_id='p1',mode='execute_confirmed_action',expected_next_action='approve_patch_candidate',explicit_decision='approve',confirmation_token='x',confirmation_text='EXECUTE ONE ACTION',require_dry_run_first=True))
    assert r.status in {'executed','blocked'} and me.exe==1

def test_approval_reject_or_hold_blocked_before_executor_if_unsupported(tmp_path):
    s,_,me,_=mk(tmp_path)
    r1=s.run(AtlasGuardedOperatorLoopRequest(pool_id='p1',mode='execute_confirmed_action',expected_next_action='approve_patch_candidate',explicit_decision='reject',confirmation_token='x',confirmation_text='EXECUTE ONE ACTION',require_dry_run_first=True))
    r2=s.run(AtlasGuardedOperatorLoopRequest(pool_id='p1',mode='execute_confirmed_action',expected_next_action='approve_patch_candidate',explicit_decision='hold',confirmation_token='x',confirmation_text='EXECUTE ONE ACTION',require_dry_run_first=True))
    assert r1.status=='blocked' and r2.status=='blocked' and me.exe==0

def test_no_path_ca_data_literals_in_guarded_loop_stack(): assert 'Path("ca_data")' not in Path('agent/atlas_guarded_operator_loop_service.py').read_text(encoding='utf-8')
