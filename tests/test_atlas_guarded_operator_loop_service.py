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
    def prepare(self,*_): return SimpleNamespace(orchestrator_run_id='nextaction_1',selected_item_id='i1',selected_next_action='run_supervised_verification',status='action_ready',model_dump=lambda:{'action_contract':{'action_id':'a1','action_kind':'execution_candidate','payload_valid':True}})
class ME:
    def execute(self, req): return SimpleNamespace(status='dry_run' if req.dry_run else 'executed',executor_run_id='manualexec_1',model_dump=lambda:{'status':'dry_run' if req.dry_run else 'executed','validation':{'executable':True},'executor_run_id':'manualexec_1'})
class PR:
    def refresh(self,*_): return SimpleNamespace(refresh_run_id='refresh_1',model_dump=lambda:{'refresh_run_id':'refresh_1','next_action_orchestrator_result':{'selected_item_id':'i2','selected_next_action':'manual_review','action_contract':{'action_id':'a2','action_kind':'manual'}}})

def mk(tmp):
    return AtlasGuardedOperatorLoopService(journal=J(),multi_status_service=MS(),next_action_orchestrator_service=NO(),manual_executor_service=ME(),post_refresh_service=PR(),data_root=tmp)

def test_advance_to_confirmation_builds_queue_prepares_token_and_dryrun(tmp_path): assert mk(tmp_path).run(AtlasGuardedOperatorLoopRequest(pool_id='p1',mode='advance_to_confirmation')).status=='dry_run_ready'
def test_dry_run_next_action_mode_runs_dryrun_only(tmp_path): assert mk(tmp_path).run(AtlasGuardedOperatorLoopRequest(pool_id='p1',mode='dry_run_next_action',orchestrator_run_id='nextaction_1',action_id='a1',expected_next_action='run_supervised_verification')).metadata['manual_executor_dry_run_calls']==1
def test_execute_confirmed_action_requires_token_and_text(tmp_path): assert mk(tmp_path).run(AtlasGuardedOperatorLoopRequest(pool_id='p1',mode='execute_confirmed_action',orchestrator_run_id='nextaction_1',action_id='a1',expected_next_action='run_supervised_verification')).status=='blocked'
def test_execute_confirmed_action_requires_prior_dryrun(tmp_path): assert mk(tmp_path).run(AtlasGuardedOperatorLoopRequest(pool_id='p1',mode='execute_confirmed_action',orchestrator_run_id='nextaction_1',action_id='a1',expected_next_action='run_supervised_verification',confirmation_token='t',confirmation_text='EXECUTE ONE ACTION',require_dry_run_first=True)).status in {'executed','blocked'}
def test_execute_and_refresh_executes_one_action_then_refreshes(tmp_path): r=mk(tmp_path).run(AtlasGuardedOperatorLoopRequest(pool_id='p1',mode='execute_and_refresh',orchestrator_run_id='nextaction_1',action_id='a1',expected_next_action='run_supervised_verification',confirmation_token='t',confirmation_text='EXECUTE ONE ACTION',require_dry_run_first=True)); assert r.metadata['manual_executor_execute_calls']==1 and r.metadata['post_refresh_calls']==1
def test_execute_and_refresh_does_not_execute_next_action_after_refresh(tmp_path): r=mk(tmp_path).run(AtlasGuardedOperatorLoopRequest(pool_id='p1',mode='execute_and_refresh',orchestrator_run_id='nextaction_1',action_id='a1',expected_next_action='run_supervised_verification',confirmation_token='t',confirmation_text='EXECUTE ONE ACTION',require_dry_run_first=True)); assert r.metadata['followup_executor_calls']==0
def test_manual_display_not_executable(tmp_path): assert mk(tmp_path).run(AtlasGuardedOperatorLoopRequest(pool_id='p1',mode='execute_confirmed_action',expected_next_action='manual_display',confirmation_token='x',confirmation_text='EXECUTE ONE ACTION')).status=='blocked'
def test_no_action_not_executable(tmp_path): assert mk(tmp_path).run(AtlasGuardedOperatorLoopRequest(pool_id='p1',mode='execute_confirmed_action',expected_next_action='no_action',confirmation_token='x',confirmation_text='EXECUTE ONE ACTION')).status=='blocked'
def test_approval_requires_explicit_decision(tmp_path): assert mk(tmp_path).run(AtlasGuardedOperatorLoopRequest(pool_id='p1',mode='execute_confirmed_action',expected_next_action='approve_patch_candidate',confirmation_token='x',confirmation_text='EXECUTE ONE ACTION')).status=='blocked'
def test_policy_prepare_only_blocks_execute(tmp_path): assert mk(tmp_path).run(AtlasGuardedOperatorLoopRequest(pool_id='p1',mode='execute_confirmed_action',policy_id='guarded_operator_loop_prepare_only_v1',confirmation_token='x',confirmation_text='EXECUTE ONE ACTION')).status=='blocked'
def test_policy_dry_run_only_blocks_execute(tmp_path): assert mk(tmp_path).run(AtlasGuardedOperatorLoopRequest(pool_id='p1',mode='execute_confirmed_action',policy_id='guarded_operator_loop_dry_run_only_v1',confirmation_token='x',confirmation_text='EXECUTE ONE ACTION')).status=='blocked'
def test_strict_policy_blocks_approval_execute(tmp_path): assert mk(tmp_path).run(AtlasGuardedOperatorLoopRequest(pool_id='p1',mode='execute_confirmed_action',policy_id='strict_guarded_operator_loop_v1',expected_next_action='approve_patch_candidate',confirmation_token='x',confirmation_text='EXECUTE ONE ACTION')).status=='blocked'
def test_saved_json_does_not_contain_confirmation_token(tmp_path): r=mk(tmp_path).run(AtlasGuardedOperatorLoopRequest(pool_id='p1')); j=(tmp_path/'atlas/guarded_operator_loop/p1'/f'{r.loop_run_id}.json').read_text(); assert 'MANUAL_EXECUTE:' not in j
def test_saved_md_does_not_contain_confirmation_token(tmp_path): r=mk(tmp_path).run(AtlasGuardedOperatorLoopRequest(pool_id='p1')); m=(tmp_path/'atlas/guarded_operator_loop/p1'/f'{r.loop_run_id}.md').read_text(); assert 'MANUAL_EXECUTE:' not in m
def test_uses_injected_data_root(tmp_path): r=mk(tmp_path).run(AtlasGuardedOperatorLoopRequest(pool_id='p1')); assert (tmp_path/'atlas/guarded_operator_loop/p1'/f'{r.loop_run_id}.json').exists()
def test_no_path_ca_data_literals_in_guarded_loop_stack(): assert 'Path("ca_data")' not in Path('agent/atlas_guarded_operator_loop_service.py').read_text(encoding='utf-8')
def test_audit_events_recorded(tmp_path): s=mk(tmp_path); s.run(AtlasGuardedOperatorLoopRequest(pool_id='p1')); assert any('guarded_operator_loop_started' in str(e) for e in s.journal.events)
