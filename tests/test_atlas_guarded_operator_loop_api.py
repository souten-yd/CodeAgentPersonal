from fastapi.testclient import TestClient
from main import app


def test_dry_run_next_action_token_shape():
    r=TestClient(app).post('/api/atlas/guarded-operator-loop/run',json={'pool_id':'p1','mode':'dry_run_next_action','orchestrator_run_id':'nextaction_1','action_id':'a1','expected_next_action':'run_supervised_verification'})
    assert r.status_code==200
    token=(r.json().get('confirmation_token') or '')
    assert (token=='') or token.startswith('MANUAL_EXECUTE:')

def test_non_executable_action_blocked():
    r=TestClient(app).post('/api/atlas/guarded-operator-loop/run',json={'pool_id':'p1','mode':'execute_confirmed_action','expected_next_action':'manual_review','confirmation_token':'x','confirmation_text':'EXECUTE ONE ACTION','require_dry_run_first':True})
    assert r.status_code==200 and r.json().get('status')=='blocked'

def test_none_action_blocked():
    r=TestClient(app).post('/api/atlas/guarded-operator-loop/run',json={'pool_id':'p1','mode':'execute_confirmed_action','expected_next_action':'none','confirmation_token':'x','confirmation_text':'EXECUTE ONE ACTION','require_dry_run_first':True})
    assert r.status_code==200 and r.json().get('status')=='blocked'

def test_approval_reject_hold_blocked_or_validated():
    c=TestClient(app)
    r1=c.post('/api/atlas/guarded-operator-loop/run',json={'pool_id':'p1','mode':'execute_confirmed_action','expected_next_action':'approve_patch_candidate','explicit_decision':'reject','confirmation_token':'x','confirmation_text':'EXECUTE ONE ACTION','require_dry_run_first':True})
    r2=c.post('/api/atlas/guarded-operator-loop/run',json={'pool_id':'p1','mode':'execute_confirmed_action','expected_next_action':'approve_patch_candidate','explicit_decision':'hold','confirmation_token':'x','confirmation_text':'EXECUTE ONE ACTION','require_dry_run_first':True})
    assert r1.status_code==200 and r2.status_code==200 and r1.json().get('status')=='blocked' and r2.json().get('status')=='blocked'
