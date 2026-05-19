from fastapi.testclient import TestClient
from main import app

def test_api_run_advance_to_confirmation(): assert TestClient(app).post('/api/atlas/guarded-operator-loop/run',json={'pool_id':'p1','mode':'advance_to_confirmation'}).status_code==200
def test_api_run_dry_run_next_action(): assert TestClient(app).post('/api/atlas/guarded-operator-loop/run',json={'pool_id':'p1','mode':'dry_run_next_action','orchestrator_run_id':'nextaction_1','action_id':'a1','expected_next_action':'run_supervised_verification'}).status_code==200
def test_api_run_execute_and_refresh(): assert TestClient(app).post('/api/atlas/guarded-operator-loop/run',json={'pool_id':'p1','mode':'execute_and_refresh','orchestrator_run_id':'nextaction_1','action_id':'a1','expected_next_action':'run_supervised_verification','confirmation_token':'x','confirmation_text':'EXECUTE ONE ACTION'}).status_code==200
def test_api_result_latest_use_request_root(): assert TestClient(app).post('/api/atlas/guarded-operator-loop/latest',json={'pool_id':'p1'}).status_code in {200,404}
def test_api_path_validation(): assert TestClient(app).post('/api/atlas/guarded-operator-loop/run',json={'pool_id':'../bad','mode':'advance_to_confirmation'}).status_code==400
def test_mode_allowlist(): assert TestClient(app).post('/api/atlas/guarded-operator-loop/run',json={'pool_id':'p1','mode':'bad'}).status_code==400
def test_expected_next_action_allowlist(): assert TestClient(app).post('/api/atlas/guarded-operator-loop/run',json={'pool_id':'p1','mode':'execute_confirmed_action','expected_next_action':'bad'}).status_code==400
def test_explicit_decision_allowlist(): assert TestClient(app).post('/api/atlas/guarded-operator-loop/run',json={'pool_id':'p1','mode':'execute_confirmed_action','explicit_decision':'bad'}).status_code==400
